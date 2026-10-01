-- of_ornament_law.lua — the ornament page-position law (promotion map D2).
--
-- Codex 0's law (profiles/40_latex_import/styles/texmf/tex/latex/codex0/
-- codex0_ornament_law.lua, Luis-ruled 2026-08-07/08) with the book removed:
-- enforced on the shipped page in pre_output_filter, not predicted from the
-- source. Each filled ornament slot carries a rule for the page top and the
-- page foot; the engine's defaults reproduce Codex 0's law, and a profile may
-- tighten a slot's rule but never loosen it (keeper ruling 01a0f99a-b2db).
--
--   top:  "keep" | "drop"                 -- stranded first on the page
--   foot: "keep_first" | "drop"           -- in the trailing run of ornaments;
--                                            "keep_first" keeps the first such
--                                            ornament and drops later ones (either/or)
--
-- Fail-safe kept: a page whose whole body is ornament is left alone.

of_ornament_law = of_ornament_law or {}
local L = of_ornament_law
L.attr = luatexbase.new_attribute("ofornamentband")
L.enabled = true
L.removed = 0
L.pages = 0
L.slots = L.slots or {}   -- [index] = { name=, top=, foot= }

local HLIST   = node.id("hlist")
local VLIST   = node.id("vlist")
local RULE    = node.id("rule")
local GLUE    = node.id("glue")
local KERN    = node.id("kern")
local PENALTY = node.id("penalty")

local logpath = os.getenv("OF_ORNAMENT_LAW_LOG")
local function say(msg)
  texio.write_nl("log", "of-ornament-law: " .. msg)
  if logpath then
    local fh = io.open(logpath, "a")
    if fh then fh:write("of-ornament-law: ", msg, "\n"); fh:close() end
  end
end
L.say = say

-- index -> name/top/foot, set from the profile by engine/ornaments.py
function L.configure(slots)
  L.slots = {}
  for index, slot in pairs(slots) do L.slots[tonumber(index)] = slot end
end

local function slot_of(cls)
  return L.slots[cls] or { name = tostring(cls), top = "drop", foot = "drop" }
end

local function is_visible_box(n)
  local id = n.id
  if id ~= HLIST and id ~= VLIST and id ~= RULE then return false end
  if id == RULE then return true end
  if n.width == 0 then return false end
  if n.height + n.depth == 0 then return false end
  return true
end

local function is_discardable(n)
  local id = n.id
  return id == GLUE or id == KERN or id == PENALTY
end

local function band_class(n)
  return node.has_attribute(n, L.attr)
end

local function page_boxes(head)
  local t = {}
  for n in node.traverse(head) do
    if is_visible_box(n) then t[#t + 1] = n end
  end
  return t
end

local function drop_box(head, b)
  local n = b.next
  while n do
    if is_discardable(n) then
      local nxt = n.next
      head = node.remove(head, n)
      node.free(n)
      n = nxt
    elseif is_visible_box(n) then
      break
    else
      n = n.next
    end
  end
  local p = b.prev
  while p do
    if is_discardable(p) then
      if band_class(p) then
        local prv = p.prev
        head = node.remove(head, p)
        node.free(p)
        p = prv
      else
        break
      end
    elseif is_visible_box(p) then
      break
    else
      p = p.prev
    end
  end
  head = node.remove(head, b)
  node.free(b)
  return head
end

local function reset_topskip(head)
  local first
  for n in node.traverse(head) do
    if is_visible_box(n) then first = n; break end
  end
  if not first then return head end
  local natural
  if tex.getglue then
    natural = tex.getglue("topskip")
  else
    local ts = tex.get("topskip")
    natural = (type(ts) == "number") and ts or ts.width
  end
  local want = natural - first.height
  if want < 0 then want = 0 end
  local g
  local n = head
  while n and n ~= first do
    if n.id == GLUE then g = n end
    n = n.next
  end
  if g then
    g.width = want
  else
    g = node.new(GLUE)
    g.width = want
    head = node.insert_before(head, first, g)
  end
  return head
end

function L.filter(head)
  if not L.enabled or head == nil then return head end
  L.pages = L.pages + 1
  local page = tex.count[0]
  local bx = page_boxes(head)
  if #bx == 0 then return head end

  local doomed, seen = {}, {}
  local function condemn(b, where, cls)
    if seen[b] then return end
    seen[b] = true
    doomed[#doomed + 1] = { node = b, where = where, cls = cls }
  end

  -- Page top: the leading run of ornaments; a slot whose top rule is "drop" goes.
  local i = 1
  while i <= #bx do
    local cls = band_class(bx[i])
    if not cls then break end
    if slot_of(cls).top == "drop" then condemn(bx[i], "top", cls) end
    i = i + 1
  end

  -- Page foot: the trailing run. "drop" goes; the first "keep_first" stays and
  -- any later one goes (the either/or).
  local run = {}
  local j = #bx
  while j >= 1 do
    local cls = band_class(bx[j])
    if not cls then break end
    table.insert(run, 1, bx[j])
    j = j - 1
  end
  local kept = nil
  for _, b in ipairs(run) do
    local cls = band_class(b)
    if slot_of(cls).foot == "drop" then
      condemn(b, "bottom", cls)
    elseif kept == nil then
      kept = cls
    else
      say(string.format("page %d: a %s and a %s both landed at the page foot; keeping the %s (either/or)",
        page, slot_of(kept).name, slot_of(cls).name, slot_of(kept).name))
      condemn(b, "bottom", cls)
    end
  end

  if #doomed == 0 then return head end
  if #doomed >= #bx then
    say(string.format("page %d: %d ornament(s) at page edges, but the page has no other content -- left alone",
      page, #doomed))
    return head
  end

  local touched_top = false
  for _, d in ipairs(doomed) do
    head = drop_box(head, d.node)
    L.removed = L.removed + 1
    if d.where == "top" then touched_top = true end
    say(string.format("page %d: dropped %s ornament stranded at %s of page", page, slot_of(d.cls).name, d.where))
  end
  if touched_top then head = reset_topskip(head) end

  local fil = node.new(GLUE)
  fil.width = 0
  fil.stretch = 65536
  fil.stretch_order = 1
  head = node.insert_after(head, node.tail(head), fil)
  return head
end

luatexbase.add_to_callback("pre_output_filter", function(head) return L.filter(head) end,
  "optical foundry ornament page-position law")
