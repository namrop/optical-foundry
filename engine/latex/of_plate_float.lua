-- of_plate_float.lua — floating plates: the pre_output_filter injector that seats each
-- full-page plate on the first legal recto after its anchor. Promotion map D3.
-- Promoted from Codex 0 (codex0_plate_float.lua: b7baf9b, c050cb3, cea2861; the
-- explanatory comments for the law are kept below and in codex0.tex). Codex 0 now
-- loads this file (its codex0_plate_float.lua is an alias), so there is one injector.
--
-- The law, in short: a plate ships as a RECTO whose facing verso lies wholly in the
-- plate's owner chapter and is not that chapter's opening page (unless the plate
-- allows it), never on a page with footnotes, never inside a divider ritual. A plate
-- that cannot find such a recto before its chapter ends fails the render.
--
-- Chapters are what \OFSetRunningTagline names (engine/latex/of_plates.tex marks
-- each call); plate pages are recorded in of_pages (D5) so page styles can drop the
-- running head on them, keyed to the page number.
of_plate_float = of_plate_float or {}
local F = of_plate_float
F.placed = F.placed or {}
F.log_prefix = F.log_prefix or "of-plate-float"

-- Markers are USER-DEFINED WHATSITS, not attributed kerns: a kern is
-- discardable and a marker that lands exactly at a page break silently
-- vanishes (proven in the 2026-08-12 probe -- the first chapter's marker and
-- a mid-page plate anchor were both dropped). Whatsits survive every break.
F.PLATE_MARK   = 0xC0DE01
F.CHAPTER_MARK = 0xC0DE02
F.RITUAL_BEGIN = 0xC0DE03
F.RITUAL_END   = 0xC0DE04
F.enabled  = true
F.queue    = {}     -- FIFO of pending plates, document order
F.chapters = {}     -- id -> tagline
F.nchapters = 0
F.chapter_now = ""  -- tagline current in SOURCE order (exact at declare time)
F.last_end = ""     -- chapter at the end of the previously shipped page
F.facing_start = "" -- chapter the previously shipped page STARTED in
F.facing_end = ""   -- chapter the previously shipped page ENDED in
F.facing_opener = false -- previously shipped page was a chapter-opening page
F.in_ritual = false -- inside a part-divider ritual (no-inject zone)
F.footins  = 0

local function say(msg)
  texio.write_nl("log", F.log_prefix .. ": " .. msg)
end

function F.set_footins(n) F.footins = n end

local USERDEF = node.subtype("user_defined")
local WHATSIT = node.id("whatsit")
local HLIST   = node.id("hlist")
local VLIST   = node.id("vlist")

local function write_mark(user_id, value)
  local n = node.new(WHATSIT, USERDEF)
  n.user_id = user_id
  n.type = 100  -- value is a number
  n.value = value
  node.write(n)
end

function F.mark_plate(id) write_mark(F.PLATE_MARK, id) end

function F.mark_ritual_begin() write_mark(F.RITUAL_BEGIN, 1) end
function F.mark_ritual_end() write_mark(F.RITUAL_END, 1) end

function F.mark_chapter(name)
  F.nchapters = F.nchapters + 1
  F.chapters[F.nchapters] = name
  F.chapter_now = name
  write_mark(F.CHAPTER_MARK, F.nchapters)
end

function F.declare(id, asset, boxnum, owner)
  -- The optional argument carries the owner and, after a '|', flags.
  -- allow-opener (Luis's "or as close as possible", 2026-08-12): a chapter too
  -- short to hold a full interior prose page has no strict seat -- The
  -- Gardener renders as a title page plus one text page in the johannah
  -- edition, so builds 72/76 terminated on it. The author opts the plate in
  -- to facing its chapter's opening page, which is the closest possible seat.
  local allow_opener = false
  local bar = owner:find("|", 1, true)
  if bar then
    local flags = owner:sub(bar + 1)
    -- trim trailing spaces without a Lua end-anchor pattern: a bare dollar
    -- sign anywhere in this file is pandoc template syntax and breaks
    -- template compilation (builds 77 and 78 -- the second time it was this
    -- very comment describing the first)
    owner = owner:sub(1, bar - 1)
    while owner:sub(-1) == " " do owner = owner:sub(1, -2) end
    allow_opener = flags:find("allow%-opener") ~= nil
  end
  if owner == "" then owner = F.chapter_now end
  table.insert(F.queue, {id = id, asset = asset, box = boxnum,
                         owner = owner, armed = false, grace = 0,
                         allow_opener = allow_opener})
  say(string.format("declared plate %d (%s), owner '%s'%s", id, asset, owner,
      allow_opener and " [allow-opener]" or ""))
end

F.plate_pages = {}   -- page number -> true, for pages the injector built

function F.is_plate_page(n)
  return F.plate_pages[n] and 1 or 0
end

function F.filter(head)
  local end_chap = F.last_end
  local page = tex.count[0]
  -- Chapter at the page START: the previous page's end -- UNLESS the first
  -- chapter marker on this page precedes any real content, i.e. the chapter
  -- opens at the top of this page (chapter-new-page makes that the normal
  -- case). Build 72's false termination: The Gardener opened at a page top,
  -- but the start proxy said the page began in the previous chapter, so no
  -- verso ever looked wholly owned and a real seat was refused.
  local start_chap = F.last_end
  local opener_page = false
  local content_seen = false
  local ritual_touch = F.in_ritual   -- true if any part of this page is ritual
  local function scan(h)
    for n in node.traverse(h) do
      if n.id == WHATSIT and n.subtype == USERDEF then
        if n.user_id == F.CHAPTER_MARK then
          local name = F.chapters[n.value] or end_chap
          if not content_seen then
            start_chap = name
            opener_page = true   -- a chapter opens at this page's top
          end
          end_chap = name
        elseif n.user_id == F.PLATE_MARK then
          for _, q in ipairs(F.queue) do
            if q.id == n.value then q.armed = true end
          end
        elseif n.user_id == F.RITUAL_BEGIN then
          F.in_ritual = true
          ritual_touch = true
        elseif n.user_id == F.RITUAL_END then
          F.in_ritual = false
        end
      elseif n.id == HLIST or n.id == VLIST then
        content_seen = true
        if n.list then scan(n.list) end
      elseif n.id == node.id("rule") then
        content_seen = true
      end
    end
  end
  scan(head)
  local p = F.queue[1]
  if F.enabled and p and p.armed then
    local odd = (page % 2 == 1)
    local foot_busy = (F.footins > 0) and (tex.box[F.footins] ~= nil)
    -- The facing verso must be ENTIRELY the owner's, not merely end in it: a
    -- chapter that opens mid-verso leaves the previous chapter's tail on that
    -- verso's upper half, and the law is about the whole spread (build 71:
    -- her-garden and the open-water plate both admitted against such versos). Wholly
    -- owned = the verso both STARTED and ENDED in the owner, with the start
    -- read from marker-before-content, not from the prior page (build 72).
    -- AND the facing verso must not be the chapter's OPENING page (Luis-ruled
    -- 2026-08-12: plates go between FULL pages, as the prose would render it
    -- -- no isolating titles, epigraphs, or first paragraphs; build 75 put
    -- plates one leaf after the Gardener and Wizards openers, splitting the
    -- epigraph spread from the body). Deferring one recto lands the plate
    -- between two full prose pages -- "or as close as possible".
    -- RITUAL NO-INJECT ZONE (build 71, Movement III divider quad on the wrong
    -- parity): the waterfall plate displaced the divider's cut-leaf recto, shoving
    -- the whole quad onto versos and forcing an internal knot re-sync. The
    -- divider leaf is the beam-cut cover-stock sheet -- its face is physical.
    -- A page any part of which belongs to a divider ritual is never displaced.
    local facing_whole = (F.facing_end == p.owner) and (F.facing_start == p.owner)
      and (p.allow_opener or not F.facing_opener)
      and not ritual_touch
    if odd and not foot_busy and facing_whole then
      table.remove(F.queue, 1)
      -- Displace this recto's content: push the whole head back onto the
      -- contribution list (it re-breaks to the same shape one page later;
      -- leading glue is discarded and \topskip re-seats, marks re-flow).
      -- PRESERVE THE BREAK REASON (build 75, vol2 folio 418): if this page
      -- was formed by a FORCED break (\clearpage / \newpage), that penalty
      -- was consumed by the page builder -- pushing the content back without
      -- it fuses the displaced page with whatever follows in the stream. The
      -- observed failure: a chapter's orphaned last line, displaced by the
      -- lamp plate, flowed straight into the divider machinery's endless-knot
      -- fill and shipped as one page. Re-append the forced penalty at the
      -- tail of the displaced content so the boundary survives the re-break.
      local tail = node.tail(head)
      local op = tex.outputpenalty or 0
      if op <= -10000 then
        local pen = node.new(node.id("penalty"))
        pen.penalty = op
        tail.next = pen
        pen.prev = tail
        tail = pen
      end
      local contrib = tex.lists.contrib_head
      tail.next = contrib
      if contrib then contrib.prev = tail end
      tex.lists.contrib_head = head
      -- Key head/folio suppression to the PAGE NUMBER, not to a flag reset at
      -- the next filter call: a \cleardoublepage or pending-float output cycle
      -- between injection and the real shipout runs extra OTR passes, and a
      -- timing flag loses the race (build 70: the waterfall plate shipped at folio
      -- 63 with 'The First Shape' still in its head). The page number survives
      -- deferred output cycles; \c@page only steps at \@outputpage.
      F.plate_pages[page] = true
      if of_pages then of_pages.mark("plate", page) end
      table.insert(F.placed, {id = p.id, asset = p.asset, owner = p.owner, page = page,
                              allow_opener = p.allow_opener})
      say(string.format(
        "page %d: plate %d (%s) shipped as this recto; facing verso is '%s'",
        page, p.id, p.asset, F.facing_end))
      -- the plate page carries no markers: for the NEXT call it reads as a
      -- page wholly inside the chapter the flow was already in
      F.facing_start = F.last_end
      F.facing_end = F.last_end
      F.facing_opener = false
      F.last_end = end_chap
      return node.copy_list(tex.box[p.box])
    end
    if odd then
      if foot_busy then
        say(string.format("page %d: plate %d deferred -- footnote insert present",
          page, p.id))
      elseif not facing_whole then
        p.grace = p.grace + 1
        say(string.format(
          "page %d: plate %d waiting -- facing verso '%s'->'%s', owner '%s' (grace %d)",
          page, p.id, F.facing_start, F.facing_end, p.owner, p.grace))
        if end_chap ~= p.owner and p.grace >= 3 then
          tex.error(string.format(
            "%s: plate %s (owner '%s') found no legal recto; "
            .. "the flow has entered '%s' at page %d. A plate may not ship "
            .. "outside its chapter (containment law, canto0 S6.1) -- move "
            .. "the anchor earlier in the chapter.",
            F.log_prefix, p.asset, p.owner, end_chap, page))
        end
      end
    end
  end
  F.facing_start = start_chap
  F.facing_end = end_chap
  F.facing_opener = opener_page
  F.last_end = end_chap
  return head
end

function F.finish()
  if #F.queue > 0 then
    local names = {}
    for _, q in ipairs(F.queue) do names[#names + 1] = q.asset end
    tex.error(F.log_prefix .. ": end of document with plate(s) never placed: "
      .. table.concat(names, ", "))
  end
end

if not F.registered then
  F.registered = true
  luatexbase.add_to_callback("pre_output_filter",
    function(head) return F.filter(head) end,
    "of floating plate injector")
end

return F
