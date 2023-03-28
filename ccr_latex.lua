tt = require('textools')
inspect = require('inspect')

function parse_authors(authors, affiliations)
    -- input authors {n1, n2} and affiliations {"a1", "{a2a, a2b}"}
    -- returns [{name="n1", affiliation={{id="1-1", name="a1"}}},
    --          {name="n1", affiliation={{if="2-1", name="a2a"}, {id="2-2", name="a2b"}}}]
    if #authors ~= #affiliations then
        io.stderr:write("Authors: " .. inspect(authors, " ") .. "\n")
        io.stderr:write("Affiliations: " .. inspect(affiliations, " ") .. "\n")
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
    local json = require('json')
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

    -- io.stderr:write(inspect(meta, " ") .. "\n")
    -- io.stderr:write(inspect(combined.meta, " ") .. "\n")

    return combined
end
