"""Two transcripts of a page are compared by content, not by LaTeX style."""
from kb_distillery.parse import compare


def keys(src):
    return " ".join(t.strict for t in compare.math_tokens(src))


def test_latex_style_does_not_matter():
    spaced = r"\mathbf { w } ^ { \star } \in \operatorname { a r g m i n } _ { \{ \mathbf { w } : \| \mathbf { w } \| \leq B \} } f ( \mathbf { w } )"
    tight = r"\mathbf{w}^\star \in \arg\min_{\{\mathbf{w}:\|\mathbf{w}\|\le B\}} f(\mathbf{w})"
    assert keys(spaced) == keys(tight)
    assert keys(r"\begin{array} { r } { \eta = \sqrt { \frac { B ^ { 2 } } { \rho ^ { 2 }   T } } } \end{array}") == \
        keys(r"\eta = \sqrt{\frac{B^2}{\rho^2 T}}")
    assert keys(r"\left( \begin{array}{cc} 1 & 0 \\ 0 & 1 \end{array} \right)") == keys(r"\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}")
    assert keys(r"0 . 2 0") == keys("0.20")
    assert keys(r"x^a_b") == keys(r"x_b^a") == keys(r"x _ { b } ^ { a }")
    assert keys(r"f'(x)") == keys(r"f^{\prime}(x)")
    assert keys(r"\bar{w}") == keys(r"\overline{w}") and keys(r"\varepsilon") == keys(r"\epsilon")


def test_content_does_matter():
    assert keys(r"x_i^2") != keys(r"x_{i^2}")                       # script level
    assert keys(r"\mathcal{T}") != keys("T") and keys(r"\mathbb{R}") != keys("R")
    assert keys(r"\mathbf{w}") != keys("w")                         # bold: strict keys differ
    assert keys(r"\hat{f}") != keys(r"\tilde{f}") and keys(r"a - b") != keys(r"a + b")
    assert keys(r"\sum_{i=1}^n") != keys(r"\sum_{i=1}^m")


def test_prose_or_maths_is_the_same_page():
    a = "Let f be a convex, ρ-Lipschitz function and T steps."
    b = "Let $f$ be a convex, $\\rho$-Lipschitz function and $T$ steps."
    assert compare.compare(a, b) == []
    assert compare.compare("*Proof.* Take **any** $x$.", "Proof. Take any $x$ .") == []


def test_a_wrong_symbol_is_found_where_it_is():
    a = "then $f ( \\bar { \\mathbf { w } } ) \\leq \\epsilon _ { \\mathrm { l } }$ , it suffices"
    b = "then $f(\\bar{\\mathbf{w}}) \\le \\epsilon$, it suffices"
    (d,) = compare.compare(a, b)
    assert d.kind == "differ" and d.a_text == "_[ l ]" and d.b_text == ""
    assert a[d.a_span[0]:d.a_span[1]].startswith("_")


def test_bold_only_and_case_only_differences_are_their_own_kind():
    (d,) = compare.compare("so $w$ holds", "so $\\mathbf{w}$ holds")
    assert d.kind == "style" and d.b_text == "w|b"
    (d,) = compare.compare("so $X_t$ holds", "so $x_t$ holds")
    assert d.kind == "case"
    assert compare.compare("so T holds", "so $t$ holds") == []       # a prose letter's case is not evidence


def test_lost_text_is_one_disagreement():
    a = "First line. Third line."
    b = "First line. Second line here. Third line."
    (d,) = compare.compare(a, b)
    assert d.a_text == "" and "s e c o n d" in d.b_text


def test_b_to_a_follows_the_alignment():
    al = compare.align("alpha beta gamma delta", "alpha beta EXTRA gamma delta")
    assert al.md_a[al.b_to_a(al.md_b.index("gamma")):].startswith("gamma")
