local M={}

function M.trim(s, what)
    -- strip whitespace from start/end of s
    if what == nil then what = "%s" end
    return s:match("^" .. what .. "*(.-)" .. what .. "*$")
end

function M.find_end_brace(s, start)
    -- get the position of an '}' in, recurively skipping over any matched {..} groups 
    -- if no brace is found, returns nil
    local brace_pos = s:find("[{}]", start)
    if brace_pos == nil then return nil end
    local brace_char = s:sub(brace_pos, brace_pos)
    if brace_char == "}" then
        return brace_pos
    else 
        close_pos = M.find_end_brace(s, brace_pos + 1)
        return M.find_end_brace(s, close_pos + 1)
    end
end

function M.strip_tex_commands(s)
    -- change 'this \emph{is} important' into 'this is important'
    while true do
        from, to = s:find("\\%a+{")
        if from == nil then break end
        local pre = s:sub(1, from - 1)
        local end_pos = M.find_end_brace(s, to + 1)
        local post = s:sub(end_pos + 1)
        local args = M.strip_tex_commands(s:sub(to + 1, end_pos - 1))
        s = pre .. args .. post
    end
    return s
end

function M.get_tex_value(s, name)
    -- Look for \name{value} and return value
    -- Handles nested arguments
    from = s:find("\\" .. name .. "{") + name:len() + 2
    to = M.find_end_brace(s, from)
    return M.trim(s:sub(from, to - 1))
end

function M.split_comma(s)
    -- split "a, {b, c}, d" into a table {"a", "{b, c}", "d"}
    local result = {}
    local position = 1
    local current_argument = ""
    while true do
        local symbol_pos = s:find("[{,]", position)
        if symbol_pos == nil then 
            -- end of string - add current argument to result and return
            current_argument =  current_argument .. s:sub(position)
            table.insert(result, M.trim(current_argument))
            return result
        end
        local symbol = s:sub(symbol_pos, symbol_pos)
        if symbol == "," then
            -- ',' --> add current argument to result
            current_argument = current_argument .. s:sub(position, symbol_pos - 1)
            table.insert(result, M.trim(current_argument))
            position = symbol_pos + 1
            current_argument = ""
        else
            -- We found a '{' --> find the closing brance and add to current argument
            end_brace = M.find_end_brace(s, symbol_pos + 1)
            current_argument = current_argument .. s:sub(position, end_brace)
            position = end_brace + 1
        end
    end
end

return M