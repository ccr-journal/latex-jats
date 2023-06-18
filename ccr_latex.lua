local tt={}


function tt.trim(s, what)
    -- strip whitespace from start/end of s
    if what == nil then what = "%s" end
    return s:match("^" .. what .. "*(.-)" .. what .. "*$")
end

function tt.find_end_brace(s, start)
    -- get the position of an '}' in, recurively skipping over any matched {..} groups
    -- if no brace is found, returns nil
    local brace_pos = s:find("[{}]", start)
    if brace_pos == nil then return nil end
    local brace_char = s:sub(brace_pos, brace_pos)
    if brace_char == "}" then
        return brace_pos
    else
        close_pos = tt.find_end_brace(s, brace_pos + 1)
        return tt.find_end_brace(s, close_pos + 1)
    end
end

function tt.strip_tex_commands(s)
    -- change 'this \emph{is} important' into 'this is important'
    while true do
        from, to = s:find("\\%a+{")
        if from == nil then break end
        local pre = s:sub(1, from - 1)
        local end_pos = tt.find_end_brace(s, to + 1)
        local post = s:sub(end_pos + 1)
        local args = tt.strip_tex_commands(s:sub(to + 1, end_pos - 1))
        s = pre .. args .. post
    end
    return s
end

function tt.get_tex_value(s, name)
    -- Look for \name{value} and return value
    -- Handles nested arguments
    from = s:find("\\" .. name .. "{") + name:len() + 2
    to = tt.find_end_brace(s, from)
    return tt.trim(s:sub(from, to - 1))
end

function tt.split_comma(s)
    -- split "a, {b, c}, d" into a table {"a", "{b, c}", "d"}
    local result = {}
    local position = 1
    local current_argument = ""
    while true do
        local symbol_pos = s:find("[{,]", position)
        if symbol_pos == nil then
            -- end of string - add current argument to result and return
            current_argument =  current_argument .. s:sub(position)
            table.insert(result, tt.trim(current_argument))
            return result
        end
        local symbol = s:sub(symbol_pos, symbol_pos)
        if symbol == "," then
            -- ',' --> add current argument to result
            current_argument = current_argument .. s:sub(position, symbol_pos - 1)
            table.insert(result, tt.trim(current_argument))
            position = symbol_pos + 1
            current_argument = ""
        else
            -- We found a '{' --> find the closing brance and add to current argument
            end_brace = tt.find_end_brace(s, symbol_pos + 1)
            current_argument = current_argument .. s:sub(position, end_brace)
            position = end_brace + 1
        end
    end
end

function parse_authors(authors, affiliations)
    -- input authors {n1, n2} and affiliations {"a1", "{a2a, a2b}"}
    -- returns [{name="n1", affiliation={{id="1-1", name="a1"}}},
    --          {name="n1", affiliation={{if="2-1", name="a2a"}, {id="2-2", name="a2b"}}}]
    if #authors ~= #affiliations then
        error('The number of authors ('..#authors..') differs from the number of affiliations (' .. #affiliations .. '). Sorry that I cant deal with this...')
    end

    local result = {}
    for i, author in ipairs(authors) do
        local aff = affiliations[i]
        if (aff:sub(1,1) == "{") and (aff:sub(-1) == "}") then
            aff = aff:sub(2, -2)
        end
        table.insert(result, {name=author, surname=author, affiliation={id=i, name=tt.trim(aff)}})
    end
    return result
end


function Reader(input)
    local meta = {}

    -- Only parse the preamble
    local tex = tostring(input)
    tex = tex:sub(1, tex:find("\\begin{document}"))

    meta["abstract"] = tt.strip_tex_commands(tt.get_tex_value(tex, "abstract"))
    meta["tags"] = tt.split_comma(tt.get_tex_value(tex, "keywords"))

    local authors = tt.split_comma(tt.get_tex_value(tex, "authorsnames"))
    local affiliations = tt.split_comma(tt.get_tex_value(tex, "authorsaffiliations"))
    meta['author'] = parse_authors(authors, affiliations)

    meta["article"] = {doi=tt.get_tex_value(tex, "doi"),
                       publisher_id=tt.get_tex_value(tex, "doi"):sub(9),
                       volume=tt.get_tex_value(tex, "volume"),
                       pubnumber=tt.get_tex_value(tex, "pubnumber"),
                       fpage=tt.get_tex_value(tex, "firstpage"),
                    }

    local year = tt.get_tex_value(tex, "pubyear")
    meta["date"] = {year=year}
    meta["copyright"] = {year=year, statement="© The author(s)", holder="The author(s)"}
    meta["license"] = {text="CC-BY 4.0", link="https://creativecommons.org/licenses/by/4.0/"}
    meta["journal"] = {title="Computational Communication Research", eissn="2665-9085", ["publisher-name"]="Amsterdam University Press"}

    local my_result = pandoc.Pandoc({}, meta)
    local default_result = pandoc.read(input, 'latex')
    local combined = default_result .. my_result

    return combined
end
