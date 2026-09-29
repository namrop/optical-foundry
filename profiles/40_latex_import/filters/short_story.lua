-- short_story.lua — source grammar for the short-story profile.
--
-- 1. A Markdown horizontal rule is a scene break: it lowers to \SSSceneBreak.
-- 2. The first paragraph of the story, and the first paragraph after a scene
--    break or a heading, starts flush left (book convention for fiction).
-- 3. The first paragraph opens with a two-line drop cap (\lettrine) unless the
--    source frontmatter sets `ss_dropcap: false`. An opening quotation mark is
--    carried as lettrine's `ante` so the initial is the first letter.
--
-- Only top-level blocks are considered: a story is a run of paragraphs. The
-- filter is a no-op for non-LaTeX output.

local OPEN_QUOTES = {
  ["\u{201C}"] = true, -- left double quotation mark
  ["\u{2018}"] = true, -- left single quotation mark
  ['"'] = true,
  ["'"] = true,
}

-- Characters that cannot appear raw inside lettrine's arguments.
local LATEX_SPECIAL = "[\\{}%%#&%$_%^~]"

local function wants_dropcap(meta)
  local value = meta.ss_dropcap
  if value == nil then
    return true
  end
  if type(value) == "boolean" then
    return value
  end
  local text = pandoc.utils.stringify(value):lower()
  return not (text == "false" or text == "no" or text == "off")
end

local function chars_of(s)
  local out = {}
  for _, code in utf8.codes(s) do
    out[#out + 1] = utf8.char(code)
  end
  return out
end

-- Splits a word into (ante, initial, rest) for \lettrine, or nil when the word
-- does not start with a character the initial can be taken from.
local function split_word(text, ante)
  local chars = chars_of(text)
  local i = 1
  if ante == "" and OPEN_QUOTES[chars[1]] then
    ante = chars[1]
    i = 2
  end
  local initial = chars[i]
  if not initial or initial:find(LATEX_SPECIAL) or initial:match("^%p$") then
    return nil
  end
  local rest = table.concat(chars, "", i + 1)
  if rest:find(LATEX_SPECIAL) then
    return nil
  end
  return ante, initial, rest
end

local function lettrine(ante, initial, rest)
  local option = ""
  if ante ~= "" then
    option = "[ante=" .. ante .. "]"
  end
  return pandoc.RawInline("latex", "\\noindent\\lettrine" .. option .. "{" .. initial .. "}{" .. rest .. "}")
end

-- Returns a new Para opening with \lettrine, or nil when the paragraph does
-- not start with a plain word the initial can be taken from. Handles a word
-- written with a literal opening quote (Str) and one inside a smart-quoted
-- span (Quoted), which is what `"...` becomes under +smart.
local function dropcap(para)
  local first = para.content[1]
  if not first then
    return nil
  end
  local content = pandoc.List()
  if first.t == "Str" then
    local ante, initial, rest = split_word(first.text, "")
    if not ante then
      return nil
    end
    content:insert(lettrine(ante, initial, rest))
  elseif first.t == "Quoted" then
    local inner = first.content
    if not inner[1] or inner[1].t ~= "Str" then
      return nil
    end
    local double = first.quotetype == "DoubleQuote"
    local open = double and "\u{201C}" or "\u{2018}"
    local close = double and "\u{201D}" or "\u{2019}"
    local ante, initial, rest = split_word(inner[1].text, open)
    if not ante then
      return nil
    end
    content:insert(lettrine(ante, initial, rest))
    for k = 2, #inner do
      content:insert(inner[k])
    end
    content:insert(pandoc.Str(close))
  else
    return nil
  end
  for k = 2, #para.content do
    content:insert(para.content[k])
  end
  return pandoc.Para(content)
end

local function flush(para)
  local content = pandoc.List({ pandoc.RawInline("latex", "\\noindent ") })
  content:extend(para.content)
  return pandoc.Para(content)
end

function Pandoc(doc)
  if not FORMAT:match("latex") then
    return nil
  end
  local use_dropcap = wants_dropcap(doc.meta)
  local blocks = pandoc.List()
  local flush_next = true
  local seen_para = false
  for _, block in ipairs(doc.blocks) do
    if block.t == "HorizontalRule" then
      blocks:insert(pandoc.RawBlock("latex", "\\SSSceneBreak"))
      flush_next = true
    elseif block.t == "Header" then
      blocks:insert(block)
      flush_next = true
    elseif block.t == "Para" then
      local out = nil
      if not seen_para and use_dropcap then
        out = dropcap(block)
      end
      if out == nil and flush_next then
        out = flush(block)
      end
      blocks:insert(out or block)
      seen_para = true
      flush_next = false
    else
      blocks:insert(block)
    end
  end
  doc.blocks = blocks
  return doc
end
