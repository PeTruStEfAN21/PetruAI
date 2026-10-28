from mdconv import to_html


def test_empty_document():
    assert to_html("") == ""
    assert to_html("\n\n  \n") == ""


def test_headings():
    assert to_html("# Title") == "<h1>Title</h1>"
    assert to_html("###### Six") == "<h6>Six</h6>"
    assert to_html("####### Seven") == "<p>####### Seven</p>"
    assert to_html("#NoSpace") == "<p>#NoSpace</p>"
    assert to_html("## Trailing  ") == "<h2>Trailing</h2>"


def test_paragraphs_join_lines_and_split_on_blank_lines():
    text = "one\ntwo\n\nthree"
    assert to_html(text) == "<p>one two</p>\n<p>three</p>"


def test_emphasis_and_strong():
    assert to_html("a *b* _c_ **d** __e__") == "<p>a <em>b</em> <em>c</em> <strong>d</strong> <strong>e</strong></p>"
    assert to_html("**bold *and italic* too**") == "<p><strong>bold <em>and italic</em> too</strong></p>"
    assert to_html("2 * 3 * 4") == "<p>2 * 3 * 4</p>"


def test_code_spans_are_literal():
    assert to_html("use `a *b* <c>`") == "<p>use <code>a *b* &lt;c&gt;</code></p>"


def test_links():
    assert to_html("see [the docs](https://x.org/a?b=1&c=2)") == (
        '<p>see <a href="https://x.org/a?b=1&amp;c=2">the docs</a></p>'
    )
    assert to_html("[**bold** link](u)") == '<p><a href="u"><strong>bold</strong> link</a></p>'


def test_html_is_escaped():
    assert to_html('5 < 6 & "q"') == "<p>5 &lt; 6 &amp; &quot;q&quot;</p>"


def test_unordered_list():
    text = "- one\n* two\n- **three**"
    assert to_html(text) == "<ul>\n<li>one</li>\n<li>two</li>\n<li><strong>three</strong></li>\n</ul>"


def test_ordered_list():
    assert to_html("1. a\n2. b\n10. c") == "<ol>\n<li>a</li>\n<li>b</li>\n<li>c</li>\n</ol>"


def test_list_type_change_starts_new_list():
    assert to_html("- a\n1. b") == "<ul>\n<li>a</li>\n</ul>\n<ol>\n<li>b</li>\n</ol>"


def test_list_ends_paragraph():
    assert to_html("intro\n- a") == "<p>intro</p>\n<ul>\n<li>a</li>\n</ul>"


def test_fenced_code_block():
    text = "```py\nx = 1 < 2\n\n*not em*\n```"
    assert to_html(text) == '<pre><code class="language-py">x = 1 &lt; 2\n\n*not em*</code></pre>'
    assert to_html("```\nplain\n```") == "<pre><code>plain</code></pre>"


def test_unclosed_fence_runs_to_the_end():
    assert to_html("```\na\nb") == "<pre><code>a\nb</code></pre>"


def test_horizontal_rule():
    assert to_html("a\n\n---\n\nb") == "<p>a</p>\n<hr>\n<p>b</p>"
    assert to_html("***") == "<hr>"


def test_blockquote_contains_blocks():
    text = "> # Quote\n> line one\n> line two\n\nafter"
    assert to_html(text) == "<blockquote>\n<h1>Quote</h1>\n<p>line one line two</p>\n</blockquote>\n<p>after</p>"


def test_nested_blockquote_and_list():
    text = "> - a\n> > deep"
    assert to_html(text) == (
        "<blockquote>\n<ul>\n<li>a</li>\n</ul>\n<blockquote>\n<p>deep</p>\n</blockquote>\n</blockquote>"
    )


def test_mixed_document():
    text = "# Doc\n\nHello *world*.\n\n- [x](y)\n- `z`\n\n```\ncode\n```\n---\nend"
    assert to_html(text) == "\n".join(
        [
            "<h1>Doc</h1>",
            "<p>Hello <em>world</em>.</p>",
            '<ul>\n<li><a href="y">x</a></li>\n<li><code>z</code></li>\n</ul>',
            "<pre><code>code</code></pre>",
            "<hr>",
            "<p>end</p>",
        ]
    )
