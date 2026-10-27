package expr

import (
	"fmt"
	"math"
)

type builtin struct {
	arity    int // -1: one or more arguments
	evaluate func(args []float64) float64
}

var builtins = map[string]builtin{
	"sqrt":  {1, func(a []float64) float64 { return math.Sqrt(a[0]) }},
	"abs":   {1, func(a []float64) float64 { return math.Abs(a[0]) }},
	"floor": {1, func(a []float64) float64 { return math.Floor(a[0]) }},
	"pow":   {2, func(a []float64) float64 { return math.Pow(a[0], a[1]) }},
	"min":   {-1, func(a []float64) float64 { return fold(a, math.Min) }},
	"max":   {-1, func(a []float64) float64 { return fold(a, math.Max) }},
}

var constants = map[string]float64{"pi": math.Pi, "e": math.E}

func fold(values []float64, pick func(a, b float64) float64) float64 {
	result := values[0]
	for _, v := range values[1:] {
		result = pick(result, v)
	}
	return result
}

func callBuiltin(name string, args []float64) (float64, error) {
	fn, ok := builtins[name]
	if !ok {
		return 0, fmt.Errorf("unknown function: %s", name)
	}
	switch {
	case fn.arity < 0 && len(args) == 0:
		return 0, fmt.Errorf("%s: want at least 1 argument, got 0", name)
	case fn.arity >= 0 && len(args) != fn.arity:
		plural := "s"
		if fn.arity == 1 {
			plural = ""
		}
		return 0, fmt.Errorf("%s: want %d argument%s, got %d", name, fn.arity, plural, len(args))
	}
	return fn.evaluate(args), nil
}
