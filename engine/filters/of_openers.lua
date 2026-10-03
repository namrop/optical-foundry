--[[
of_openers.lua — chapter-opener capitals (promotion map D4), added by engine/openers.py
when a render's profile declares `openers:`. Configuration in metadata `of_openers`
(JSON): { "capital": "raised" | "none" }.

An opener is detected from the raw LaTeX the bundle compiler writes for it: the
chapter's \addcontentsline{toc}{subsection}{...}, or an \OFSetRunningTagline{...}.
(\OFChapterOpener itself is expanded away by pandoc's latex_macros before filters run.)

Rules, Codex 0's (CHAPTER_OPENERS_CONTRACT.md, rulings 2026-08-03):
  * the first prose paragraph after an opener gets \OFOpenerCapital{L}{rest};
  * leading raw inlines (a rail begin) are stepped over;
  * a letter inside an opening colour macro (raw "\Name{") gets \OFOpenerCapitalInherit;
  * an opening block quote (epigraph) is skipped: the prose beneath it is lettered;
  * a verse (LineBlock) or heading opener gets no capital;
  * anything not starting with an ASCII letter keeps a plain opening (fail-open).
]]

local capital = "raised"

function Meta(meta)
  local raw = meta.of_openers and pandoc.utils.stringify(meta.of_openers) or nil
  if raw and raw ~= "" then
    local ok, cfg = pcall(pandoc.json.decode, raw)
    if ok and type(cfg) == "table" and cfg.capital then capital = cfg.capital end
  end
end

local function is_opener(b)
  if b.t ~= "RawBlock" or (b.format ~= "latex" and b.format ~= "tex") then return false end
  if b.text:find("providecommand", 1, true) then return false end
  return b.text:find("\\addcontentsline{toc}{subsection}{", 1, true) ~= nil
      or b.text:find("\\OFSetRunningTagline{", 1, true) ~= nil
end

local function letter_word(inl, i, macro)
  local s = inl[i].text
  local first = s:sub(1, 1)
  if not first:match("^%a$") then return false end
  inl[i] = pandoc.RawInline("latex", string.format("\\%s{%s}{%s}", macro, first, s:sub(2)))
  return true
end

local function apply(para)
  local inl = para.content
  local i = 1
  while i <= #inl do
    local n = inl[i]
    if n.t == "Str" then
      local prev = (i > 1) and inl[i - 1] or nil
      local inside = prev and prev.t == "RawInline" and prev.text:match("^\\%a+%{$") ~= nil
      return letter_word(inl, i, inside and "OFOpenerCapitalInherit" or "OFOpenerCapital")
    elseif (n.t == "RawInline" and (n.format == "latex" or n.format == "tex")) or n.t == "Space" then
      i = i + 1
    elseif n.t == "Emph" or n.t == "Strong" then
      local inner = n.content
      if #inner > 0 and inner[1].t == "Str" and letter_word(inner, 1, "OFOpenerCapital") then
        n.content = inner
        inl[i] = n
        return true
      end
      return false
    else
      return false
    end
  end
  return false
end

-- true once the opener's paragraph was decided (lettered or deliberately bare)
local function first_para(blocks)
  for _, b in ipairs(blocks) do
    if b.t == "Para" then
      apply(b)
      return true
    elseif b.t == "Div" then
      if first_para(b.content) then return true end
    elseif b.t == "LineBlock" or b.t == "Header" then
      return true
    end
    -- BlockQuote (an epigraph) and anything else: keep looking
  end
  return false
end

function Pandoc(doc)
  if capital == "none" then return doc end
  local pending = false
  for _, b in ipairs(doc.blocks) do
    if is_opener(b) then
      pending = true
    elseif pending then
      if b.t == "Para" then
        apply(b)
        pending = false
      elseif b.t == "Div" then
        if first_para(b.content) then pending = false end
      elseif b.t == "LineBlock" or b.t == "Header" then
        pending = false
      end
    end
  end
  return doc
end
