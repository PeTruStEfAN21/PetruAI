package expr

import (
	"fmt"
	"strings"
)

// Interpreter keeps variables between lines: "name = expr" assigns, anything else evaluates.
type Interpreter struct {
	Vars map[string]float64
}

func NewInterpreter() *Interpreter {
	vars := make(map[string]float64, len(constants))
	for name, value := range constants {
		vars[name] = value
	}
	return &Interpreter{Vars: vars}
}

func (in *Interpreter) Exec(line string) (float64, error) {
	tokens, err := lex(line)
	if err != nil {
		return 0, err
	}
	if len(tokens) >= 2 && tokens[0].kind == tokIdent && tokens[1].kind == tokAssign {
		name := tokens[0].text
		if _, constant := constants[name]; constant {
			return 0, fmt.Errorf("cannot assign to constant %s", name)
		}
		rest := line[tokens[1].pos+1:]
		if strings.TrimSpace(rest) == "" {
			return 0, &SyntaxError{Pos: len(line), Msg: "unexpected end of input"}
		}
		value, err := Eval(rest, in.Vars)
		if err != nil {
			return 0, err
		}
		in.Vars[name] = value
		return value, nil
	}
	return Eval(line, in.Vars)
}
