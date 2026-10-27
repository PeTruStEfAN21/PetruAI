package expr

import (
	"errors"
	"math"
	"testing"
)

func TestEvalArithmetic(t *testing.T) {
	cases := map[string]float64{
		"1 + 2 * 3":       7,
		"(1 + 2) * 3":     9,
		"10 / 4":          2.5,
		"10 % 4":          2,
		"2 ^ 3 ^ 2":       512,
		"-2 ^ 2":          -4,
		"--3":             3,
		"1.5e2 + .5":      150.5,
		"8 - 3 - 2":       3,
		"2 * -3":          -6,
		"  42  ":          42,
		"sqrt(16) + abs(-2)": 6,
		"min(3, 1, 2)":    1,
		"max(1, 2 + 3)":   5,
		"floor(2.7)":      2,
		"pow(2, 10)":      1024,
	}
	for src, want := range cases {
		got, err := Eval(src, nil)
		if err != nil {
			t.Errorf("Eval(%q) error: %v", src, err)
			continue
		}
		if math.Abs(got-want) > 1e-9 {
			t.Errorf("Eval(%q) = %v, want %v", src, got, want)
		}
	}
}

func TestEvalVariables(t *testing.T) {
	env := map[string]float64{"x": 3, "rate_2": 0.5}
	got, err := Eval("x * x + rate_2", env)
	if err != nil || got != 9.5 {
		t.Fatalf("got %v, %v", got, err)
	}
	_, err = Eval("y + 1", env)
	var undef *UndefinedError
	if !errors.As(err, &undef) || undef.Name != "y" {
		t.Fatalf("want UndefinedError for y, got %v", err)
	}
	if err.Error() != "undefined variable: y" {
		t.Fatalf("message: %q", err.Error())
	}
}

func TestEvalErrors(t *testing.T) {
	if _, err := Eval("1 / (2 - 2)", nil); !errors.Is(err, ErrDivisionByZero) {
		t.Errorf("division: %v", err)
	}
	if _, err := Eval("5 % 0", nil); !errors.Is(err, ErrDivisionByZero) {
		t.Errorf("modulo: %v", err)
	}
	if _, err := Eval("nope(1)", nil); err == nil || err.Error() != "unknown function: nope" {
		t.Errorf("unknown function: %v", err)
	}
	if _, err := Eval("sqrt(1, 2)", nil); err == nil || err.Error() != "sqrt: want 1 argument, got 2" {
		t.Errorf("arity: %v", err)
	}
	if _, err := Eval("min()", nil); err == nil || err.Error() != "min: want at least 1 argument, got 0" {
		t.Errorf("variadic arity: %v", err)
	}
}

func TestSyntaxErrors(t *testing.T) {
	cases := []struct {
		src string
		pos int
		msg string
	}{
		{"1 +", 3, "unexpected end of input"},
		{"(1", 2, "expected )"},
		{"1 $ 2", 2, "unexpected character '$'"},
		{"1 2", 2, "unexpected 2"},
		{"", 0, "unexpected end of input"},
		{"max(1,", 6, "unexpected end of input"},
		{")", 0, "unexpected )"},
	}
	for _, c := range cases {
		_, err := Parse(c.src)
		var syn *SyntaxError
		if !errors.As(err, &syn) {
			t.Errorf("Parse(%q): want SyntaxError, got %v", c.src, err)
			continue
		}
		if syn.Pos != c.pos || syn.Msg != c.msg {
			t.Errorf("Parse(%q) = (%d, %q), want (%d, %q)", c.src, syn.Pos, syn.Msg, c.pos, c.msg)
		}
	}
	_, err := Parse("1 +")
	if err.Error() != "syntax error at 3: unexpected end of input" {
		t.Errorf("message: %q", err.Error())
	}
}

func TestString(t *testing.T) {
	cases := map[string]string{
		"1 + 2 * 3":         "(1 + (2 * 3))",
		"-x ^ 2":            "(-(x ^ 2))",
		"max(1, a / 2.5)":   "max(1, (a / 2.5))",
		"2 ^ 3 ^ 2":         "(2 ^ (3 ^ 2))",
		"((7))":             "7",
	}
	for src, want := range cases {
		node, err := Parse(src)
		if err != nil {
			t.Errorf("Parse(%q): %v", src, err)
			continue
		}
		if got := node.String(); got != want {
			t.Errorf("Parse(%q).String() = %q, want %q", src, got, want)
		}
	}
}

func TestInterpreter(t *testing.T) {
	in := NewInterpreter()
	steps := []struct {
		line string
		want float64
	}{
		{"x = 4", 4},
		{"y = x * 2 + 1", 9},
		{"x = x + 1", 5},
		{"x + y", 14},
		{"pi * 0", 0},
	}
	for _, s := range steps {
		got, err := in.Exec(s.line)
		if err != nil || got != s.want {
			t.Fatalf("Exec(%q) = %v, %v; want %v", s.line, got, err, s.want)
		}
	}
	if in.Vars["x"] != 5 || in.Vars["y"] != 9 {
		t.Fatalf("vars: %v", in.Vars)
	}
	if _, err := in.Exec("z = q"); err == nil {
		t.Fatal("undefined q must fail")
	}
	if _, ok := in.Vars["z"]; ok {
		t.Fatal("a failed assignment must not define z")
	}
	if _, err := in.Exec("pi = 3"); err == nil || err.Error() != "cannot assign to constant pi" {
		t.Fatalf("constant: %v", err)
	}
	if math.Abs(in.Vars["pi"]-math.Pi) > 0 {
		t.Fatal("pi must stay math.Pi")
	}
}
