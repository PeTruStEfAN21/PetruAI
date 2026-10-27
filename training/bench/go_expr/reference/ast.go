package expr

import (
	"strconv"
	"strings"
)

// Node is a parsed expression; String prints it fully parenthesized.
type Node interface {
	String() string
}

type Number struct{ Value float64 }

type Variable struct{ Name string }

type Unary struct {
	Op      string
	Operand Node
}

type Binary struct {
	Op          string
	Left, Right Node
}

type Call struct {
	Func string
	Args []Node
}

func (n Number) String() string   { return strconv.FormatFloat(n.Value, 'g', -1, 64) }
func (v Variable) String() string { return v.Name }
func (u Unary) String() string    { return "(" + u.Op + u.Operand.String() + ")" }
func (b Binary) String() string {
	return "(" + b.Left.String() + " " + b.Op + " " + b.Right.String() + ")"
}

func (c Call) String() string {
	args := make([]string, len(c.Args))
	for i, a := range c.Args {
		args[i] = a.String()
	}
	return c.Func + "(" + strings.Join(args, ", ") + ")"
}
