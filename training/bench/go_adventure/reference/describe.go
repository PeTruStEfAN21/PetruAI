package adventure

import (
	"sort"
	"strings"
)

func sortedCopy(items []string) []string {
	out := append([]string(nil), items...)
	sort.Strings(out)
	return out
}

// describe prints a room: its description, its exits and, when there are any, its items.
func describe(room Room, items []string) string {
	lines := []string{room.Description, "Exits: " + strings.Join(sortedKeys(room.Exits), ", ")}
	if len(items) > 0 {
		lines = append(lines, "You see: "+strings.Join(sortedCopy(items), ", "))
	}
	return strings.Join(lines, "\n")
}

func describeInventory(items []string) string {
	if len(items) == 0 {
		return "You are carrying nothing."
	}
	return "You are carrying: " + strings.Join(sortedCopy(items), ", ")
}
