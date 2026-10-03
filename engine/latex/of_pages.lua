-- of_pages.lua — page-number-keyed page marks and the shipped-page ledger.
-- Promotion map D5 (Codex 0 c050cb3): suppression keyed to the PAGE NUMBER, not to a
-- flag reset at the next output cycle. A page the output routine builds itself (a
-- floating plate) is marked here when it is built; the page style asks at shipout.
-- A deferred output cycle between the two cannot desynchronise them, because the page
-- number only steps at \@outputpage (Codex 0 build 70: a plate shipped with the
-- previous chapter's head when a timing flag was used instead).
--
-- The ledger records every page as it ships: its physical index, its folio label, the
-- chapter it starts and ends in (from of_plate_float's chapter whatsits) and its marks.
-- engine/plates.py reads it (from the PDF's Info dictionary, see P.hex) to check the
-- placement law independently of the code that placed the plates: it sees what
-- shipped, not what was intended.
of_pages = of_pages or {}
local P = of_pages

P.marks = P.marks or {}     -- class -> {page number -> true}
P.ledger = P.ledger or {}
P.ledger_path = P.ledger_path or nil
P.CHAPTER_MARK = 0xC0DE02   -- shared with of_plate_float (same whatsit ids as Codex 0)

function P.mark(class, n)
  P.marks[class] = P.marks[class] or {}
  P.marks[class][n] = true
end

function P.is(class, n)
  local m = P.marks[class]
  return (m and m[n]) and 1 or 0
end

local USERDEF = node.subtype("user_defined")
local WHATSIT = node.id("whatsit")
local HLIST   = node.id("hlist")
local VLIST   = node.id("vlist")

P.last_end = ""

-- Walk a page body for chapter whatsits, exactly as of_plate_float's filter does:
-- start = the first marker when it precedes any content (the chapter opens at this
-- page's top), else the previous page's end; end = the last marker.
local RULE = node.id("rule")
local function chapters(head, names)
  local start_chap, end_chap = P.last_end, P.last_end
  local content_seen = false
  local opener = false
  local function scan(h)
    for n in node.traverse(h) do
      if n.id == WHATSIT and n.subtype == USERDEF and n.user_id == P.CHAPTER_MARK then
        local name = names[n.value] or end_chap
        if not content_seen then start_chap = name; opener = true end
        end_chap = name
      elseif n.id == HLIST or n.id == VLIST then
        content_seen = true
        if n.list then scan(n.list) end
      elseif n.id == RULE then
        content_seen = true
      end
    end
  end
  if head then scan(head) end
  return start_chap, end_chap, opener
end

-- Called from the start of \@outputpage (of_plates.tex), once per shipped page, with
-- the page body box (\@outputbox) and the folio as the page will print it.
function P.record(boxnum, label)
  local page = tex.count[0]
  local box = tex.box[boxnum]
  local names = (of_plate_float and of_plate_float.chapters) or {}
  local s, e, opener = chapters(box and box.list, names)
  local entry = {index = #P.ledger + 1, page = page, label = label or tostring(page),
                 start = s, ["end"] = e, opener = opener, marks = {}}
  for class, pages in pairs(P.marks) do
    if pages[page] then table.insert(entry.marks, class) end
  end
  table.insert(P.ledger, entry)
  P.last_end = e
end

local function q(s)
  s = tostring(s or "")
  s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", " ")
  return '"' .. s .. '"'
end

function P.json()
  local out = {'{"schema_version": "page_ledger_v1", "pages": ['}
  for i, e in ipairs(P.ledger) do
    local marks = {}
    for _, m in ipairs(e.marks) do marks[#marks + 1] = q(m) end
    out[#out + 1] = string.format('{"index": %d, "page": %d, "label": %s, "start": %s, "end": %s, "opener": %s, "marks": [%s]}%s',
      e.index, e.page, q(e.label), q(e.start), q(e["end"]), e.opener and "true" or "false",
      table.concat(marks, ", "), i < #P.ledger and "," or "")
  end
  local plates = {}
  for _, p in ipairs((of_plate_float and of_plate_float.placed) or {}) do
    plates[#plates + 1] = string.format('{"id": %d, "asset": %s, "owner": %s, "page": %d, "allow_opener": %s}',
      p.id, q(p.asset), q(p.owner), p.page, p.allow_opener and "true" or "false")
  end
  local pending = {}
  for _, p in ipairs((of_plate_float and of_plate_float.queue) or {}) do
    pending[#pending + 1] = q(p.asset)
  end
  out[#out + 1] = '], "plates": [' .. table.concat(plates, ", ") .. '], "unplaced": [' .. table.concat(pending, ", ") .. ']}'
  return table.concat(out, "\n")
end

-- The ledger leaves the run inside the PDF: pandoc compiles in a temporary
-- directory and sets TEXMFOUTPUT to it, so with openout_any=p a file written
-- anywhere else is refused, and the temporary directory is deleted afterwards.
-- The JSON is hex-encoded so the Info value is plain ASCII (no PDF string
-- escaping, UTF-8 chapter titles intact); engine/plates.py reads it and strips it.
function P.hex()
  return (P.json():gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

-- Direct lualatex runs (no pandoc) may still ask for a file.
function P.write()
  if not P.ledger_path then return end
  local f = io.open(P.ledger_path, "w")
  if not f then
    texio.write_nl("log", "of-pages: cannot write " .. P.ledger_path)
    return
  end
  f:write(P.json() .. "\n")
  f:close()
end

return P
