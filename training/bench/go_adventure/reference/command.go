package adventure

import "strings"

type command struct {
	verb string // look, go, take, drop, inventory, or "" when not understood
	arg  string
	raw  string
}

var directionAliases = map[string]string{
	"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down",
}

var verbAliases = map[string]string{
	"look": "look", "l": "look",
	"go": "go", "walk": "go",
	"take": "take", "get": "take",
	"drop": "drop",
	"inventory": "inventory", "i": "inventory", "inv": "inventory",
}

func isDirection(word string) bool {
	switch word {
	case "north", "south", "east", "west", "up", "down":
		return true
	}
	return false
}

func normalizeDirection(word string) string {
	if full, ok := directionAliases[word]; ok {
		return full
	}
	return word
}

// parse reads one line: case and extra spaces do not matter, a bare direction means "go".
func parse(line string) command {
	raw := strings.TrimSpace(line)
	words := strings.Fields(strings.ToLower(raw))
	if len(words) == 0 {
		return command{raw: raw}
	}
	first, rest := words[0], strings.Join(words[1:], " ")
	if dir := normalizeDirection(first); isDirection(dir) && rest == "" {
		return command{verb: "go", arg: dir, raw: raw}
	}
	verb, ok := verbAliases[first]
	if !ok {
		return command{verb: "", raw: raw}
	}
	if verb == "go" {
		rest = normalizeDirection(rest)
	}
	return command{verb: verb, arg: rest, raw: raw}
}
