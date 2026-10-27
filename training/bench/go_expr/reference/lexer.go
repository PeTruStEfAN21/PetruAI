package expr

import (
	"fmt"
	"strconv"
	"unicode"
)

type tokenKind int

const (
	tokEOF tokenKind = iota
	tokNumber
	tokIdent
	tokOp
	tokLParen
	tokRParen
	tokComma
	tokAssign
)

type token struct {
	kind tokenKind
	text string
	num  float64
	pos  int
}

func (t token) describe() string {
	if t.kind == tokEOF {
		return "end of input"
	}
	return t.text
}

// lex splits src into tokens; the last one is always tokEOF at len(src).
func lex(src string) ([]token, error) {
	var tokens []token
	runes := []rune(src)
	offset := func(i int) int { return len(string(runes[:i])) }
	for i := 0; i < len(runes); {
		r := runes[i]
		switch {
		case unicode.IsSpace(r):
			i++
		case unicode.IsDigit(r) || (r == '.' && i+1 < len(runes) && unicode.IsDigit(runes[i+1])):
			start := i
			for i < len(runes) && (unicode.IsDigit(runes[i]) || runes[i] == '.') {
				i++
			}
			if i < len(runes) && (runes[i] == 'e' || runes[i] == 'E') {
				j := i + 1
				if j < len(runes) && (runes[j] == '+' || runes[j] == '-') {
					j++
				}
				if j < len(runes) && unicode.IsDigit(runes[j]) {
					i = j
					for i < len(runes) && unicode.IsDigit(runes[i]) {
						i++
					}
				}
			}
			text := string(runes[start:i])
			num, err := strconv.ParseFloat(text, 64)
			if err != nil {
				return nil, &SyntaxError{Pos: offset(start), Msg: fmt.Sprintf("bad number %s", text)}
			}
			tokens = append(tokens, token{tokNumber, text, num, offset(start)})
		case unicode.IsLetter(r) || r == '_':
			start := i
			for i < len(runes) && (unicode.IsLetter(runes[i]) || unicode.IsDigit(runes[i]) || runes[i] == '_') {
				i++
			}
			tokens = append(tokens, token{tokIdent, string(runes[start:i]), 0, offset(start)})
		default:
			kinds := map[rune]tokenKind{
				'+': tokOp, '-': tokOp, '*': tokOp, '/': tokOp, '%': tokOp, '^': tokOp,
				'(': tokLParen, ')': tokRParen, ',': tokComma, '=': tokAssign,
			}
			kind, ok := kinds[r]
			if !ok {
				return nil, &SyntaxError{Pos: offset(i), Msg: fmt.Sprintf("unexpected character '%c'", r)}
			}
			tokens = append(tokens, token{kind, string(r), 0, offset(i)})
			i++
		}
	}
	return append(tokens, token{tokEOF, "", 0, len(src)}), nil
}
