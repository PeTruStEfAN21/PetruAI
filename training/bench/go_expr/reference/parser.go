package expr

import "fmt"

// SyntaxError reports where parsing stopped; Pos is a byte offset into the source.
type SyntaxError struct {
	Pos int
	Msg string
}

func (e *SyntaxError) Error() string { return fmt.Sprintf("syntax error at %d: %s", e.Pos, e.Msg) }

// Grammar, lowest precedence first:
//
//	expr    = term { ("+" | "-") term }
//	term    = unary { ("*" | "/" | "%") unary }
//	unary   = "-" unary | power
//	power   = primary [ "^" unary ]        (right associative, binds tighter than unary minus on its left)
//	primary = number | ident | ident "(" [ expr { "," expr } ] ")" | "(" expr ")"
type parser struct {
	tokens []token
	pos    int
}

func Parse(src string) (Node, error) {
	tokens, err := lex(src)
	if err != nil {
		return nil, err
	}
	p := &parser{tokens: tokens}
	node, err := p.expr()
	if err != nil {
		return nil, err
	}
	if tok := p.peek(); tok.kind != tokEOF {
		return nil, p.unexpected(tok)
	}
	return node, nil
}

func (p *parser) peek() token { return p.tokens[p.pos] }

func (p *parser) next() token {
	tok := p.tokens[p.pos]
	if tok.kind != tokEOF {
		p.pos++
	}
	return tok
}

func (p *parser) unexpected(tok token) error {
	return &SyntaxError{Pos: tok.pos, Msg: "unexpected " + tok.describe()}
}

func (p *parser) isOp(ops ...string) bool {
	tok := p.peek()
	if tok.kind != tokOp {
		return false
	}
	for _, op := range ops {
		if tok.text == op {
			return true
		}
	}
	return false
}

func (p *parser) expr() (Node, error) {
	left, err := p.term()
	for err == nil && p.isOp("+", "-") {
		op := p.next().text
		var right Node
		if right, err = p.term(); err == nil {
			left = Binary{op, left, right}
		}
	}
	return left, err
}

func (p *parser) term() (Node, error) {
	left, err := p.unary()
	for err == nil && p.isOp("*", "/", "%") {
		op := p.next().text
		var right Node
		if right, err = p.unary(); err == nil {
			left = Binary{op, left, right}
		}
	}
	return left, err
}

func (p *parser) unary() (Node, error) {
	if p.isOp("-") {
		p.next()
		operand, err := p.unary()
		if err != nil {
			return nil, err
		}
		return Unary{"-", operand}, nil
	}
	return p.power()
}

func (p *parser) power() (Node, error) {
	base, err := p.primary()
	if err != nil || !p.isOp("^") {
		return base, err
	}
	p.next()
	exponent, err := p.unary()
	if err != nil {
		return nil, err
	}
	return Binary{"^", base, exponent}, nil
}

func (p *parser) primary() (Node, error) {
	tok := p.next()
	switch tok.kind {
	case tokNumber:
		return Number{tok.num}, nil
	case tokIdent:
		if p.peek().kind != tokLParen {
			return Variable{tok.text}, nil
		}
		p.next()
		return p.call(tok.text)
	case tokLParen:
		inner, err := p.expr()
		if err != nil {
			return nil, err
		}
		if closing := p.peek(); closing.kind != tokRParen {
			return nil, &SyntaxError{Pos: closing.pos, Msg: "expected )"}
		}
		p.next()
		return inner, nil
	}
	return nil, p.unexpected(tok)
}

func (p *parser) call(name string) (Node, error) {
	call := Call{Func: name}
	if p.peek().kind == tokRParen {
		p.next()
		return call, nil
	}
	for {
		arg, err := p.expr()
		if err != nil {
			return nil, err
		}
		call.Args = append(call.Args, arg)
		switch tok := p.next(); tok.kind {
		case tokComma:
			continue
		case tokRParen:
			return call, nil
		default:
			return nil, &SyntaxError{Pos: tok.pos, Msg: "expected , or )"}
		}
	}
}
