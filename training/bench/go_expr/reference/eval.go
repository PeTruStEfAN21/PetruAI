package expr

import (
	"errors"
	"fmt"
	"math"
)

var ErrDivisionByZero = errors.New("division by zero")

type UndefinedError struct{ Name string }

func (e *UndefinedError) Error() string { return "undefined variable: " + e.Name }

// Eval parses and evaluates src; variables come from env, then from the constants (pi, e).
func Eval(src string, env map[string]float64) (float64, error) {
	node, err := Parse(src)
	if err != nil {
		return 0, err
	}
	return evaluate(node, env)
}

func evaluate(node Node, env map[string]float64) (float64, error) {
	switch n := node.(type) {
	case Number:
		return n.Value, nil
	case Variable:
		if v, ok := env[n.Name]; ok {
			return v, nil
		}
		if v, ok := constants[n.Name]; ok {
			return v, nil
		}
		return 0, &UndefinedError{n.Name}
	case Unary:
		v, err := evaluate(n.Operand, env)
		return -v, err
	case Binary:
		left, err := evaluate(n.Left, env)
		if err != nil {
			return 0, err
		}
		right, err := evaluate(n.Right, env)
		if err != nil {
			return 0, err
		}
		return applyBinary(n.Op, left, right)
	case Call:
		args := make([]float64, len(n.Args))
		for i, arg := range n.Args {
			v, err := evaluate(arg, env)
			if err != nil {
				return 0, err
			}
			args[i] = v
		}
		return callBuiltin(n.Func, args)
	}
	return 0, fmt.Errorf("unknown node %T", node)
}

func applyBinary(op string, a, b float64) (float64, error) {
	switch op {
	case "+":
		return a + b, nil
	case "-":
		return a - b, nil
	case "*":
		return a * b, nil
	case "/":
		if b == 0 {
			return 0, ErrDivisionByZero
		}
		return a / b, nil
	case "%":
		if b == 0 {
			return 0, ErrDivisionByZero
		}
		return math.Mod(a, b), nil
	case "^":
		return math.Pow(a, b), nil
	}
	return 0, fmt.Errorf("unknown operator %s", op)
}
