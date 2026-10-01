--[[
of_ornaments.lua — the authoring surface for a profile's ornament slots.

Pandoc Lua filter added by engine/ornaments.py when a render's profile package
fills ornament slots. Its configuration comes in the metadata field
`of_ornaments` (JSON, written by the engine):

  { "rail": { "class": "literal-voice", "run_key": null },
    "slots": { "breath": {"class": "breath", "index": 2}, ... } }

* A Div carrying the rail class is a marked block (keeper ruling 01a0f99a-b2db:
  marked by hand). It is wrapped in \OFRailBegin{seg}{run} ... \OFRailEnd{seg}{run}.
  seg is one per block (the draw extent); run is the family: consecutive marked
  blocks share a run until a chapter or part starts, or, when the profile names
  a run_key attribute, until that attribute's value changes (Codex 0's story=).
* A Div carrying a slot's class (an empty one: `::: breath :::`) becomes
  \OFOrnament{<slot>}, which prints the slot's art if the profile filled it.

Chapter and part starts are read from the assembled bundle: a raw LaTeX block
naming \addcontentsline{toc}, \OFSetRunningTagline or \OFSetRunningDivision, or a
level-1 heading.
]]

local cfg = { rail = nil, slots = {} }
local class_to_slot = {}
local seg, run = 0, 0
local open_run = false
local last_key = nil

local function has_class(el, name)
  for _, c in ipairs(el.classes) do if c == name then return true end end
  return false
end

local function boundary()
  open_run = false
  last_key = nil
end

function Meta(meta)
  local raw = meta.of_ornaments
  if raw then
    local text = pandoc.utils.stringify(raw)
    local ok, parsed = pcall(pandoc.json.decode, text)
    if ok and parsed then
      cfg.rail = parsed.rail
      cfg.slots = parsed.slots or {}
      for name, slot in pairs(cfg.slots) do class_to_slot[slot.class or name] = name end
    end
  end
  return meta
end

local function raw(tex) return pandoc.RawBlock("latex", tex) end

local function is_boundary_raw(text)
  return text:find("\\addcontentsline{toc}", 1, true)
      or text:find("\\OFSetRunningTagline", 1, true)
      or text:find("\\OFSetRunningDivision", 1, true)
end

local function walk(blocks)
  local out = pandoc.List()
  for _, el in ipairs(blocks) do
    if el.t == "RawBlock" and (el.format == "latex" or el.format == "tex") and is_boundary_raw(el.text) then
      boundary()
      out:insert(el)
    elseif el.t == "Header" and el.level == 1 then
      boundary()
      out:insert(el)
    elseif el.t == "Div" and cfg.rail and has_class(el, cfg.rail.class) then
      local key = cfg.rail.run_key and el.attributes[cfg.rail.run_key] or nil
      if not open_run or (cfg.rail.run_key and key ~= last_key) then
        run = run + 1
        open_run = true
        last_key = key
      end
      seg = seg + 1
      out:insert(raw(string.format("\\OFRailBegin{%d}{%d}", seg, run)))
      out:extend(walk(el.content))
      out:insert(raw(string.format("\\OFRailEnd{%d}{%d}", seg, run)))
    elseif el.t == "Div" then
      local slot = nil
      for _, c in ipairs(el.classes) do
        if class_to_slot[c] then slot = class_to_slot[c] break end
      end
      if slot then
        out:insert(raw(string.format("\\OFOrnament{%s}", slot)))
        out:extend(walk(el.content))
      else
        el.content = walk(el.content)
        out:insert(el)
      end
    elseif el.t == "BlockQuote" then
      el.content = walk(el.content)
      out:insert(el)
    else
      out:insert(el)
    end
  end
  return out
end

function Pandoc(doc)
  Meta(doc.meta)
  doc.blocks = walk(doc.blocks)
  return doc
end

return { { Pandoc = Pandoc } }
