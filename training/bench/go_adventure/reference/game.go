package adventure

import (
	"fmt"
	"slices"
)

// Game is one play-through of a World: where the player is, what they carry, what lies where.
type Game struct {
	world     *World
	room      string
	inventory []string
	items     map[string][]string
	moves     int
	won       bool
}

func NewGame(w *World) *Game {
	return &Game{world: w, room: w.Start, items: w.initialItems()}
}

func (g *Game) Room() string { return g.room }
func (g *Game) Moves() int   { return g.moves }
func (g *Game) Won() bool    { return g.won }

// Do runs one command line and returns what the player sees.
func (g *Game) Do(line string) string {
	if g.won {
		return "The game is over."
	}
	cmd := parse(line)
	switch cmd.verb {
	case "look":
		return g.look()
	case "go":
		return g.goTo(cmd.arg)
	case "take":
		return g.take(cmd.arg)
	case "drop":
		return g.drop(cmd.arg)
	case "inventory":
		return describeInventory(g.inventory)
	}
	if cmd.raw == "" {
		return "Say something."
	}
	return fmt.Sprintf("I don't understand %q.", cmd.raw)
}

func (g *Game) look() string {
	return describe(g.world.Rooms[g.room], g.items[g.room])
}

func (g *Game) goTo(dir string) string {
	if dir == "" {
		return "Go where?"
	}
	target, ok := g.world.Rooms[g.room].Exits[dir]
	if !ok {
		return fmt.Sprintf("You can't go %s.", dir)
	}
	if key := g.world.Rooms[target].LockedBy; key != "" && !slices.Contains(g.inventory, key) {
		return fmt.Sprintf("The way %s is locked. You need the %s.", dir, key)
	}
	g.room = target
	g.moves++
	view := g.look()
	if target == g.world.Goal {
		g.won = true
		view += "\nYou win!"
	}
	return view
}

func (g *Game) take(item string) string {
	if item == "" {
		return "Take what?"
	}
	here := g.items[g.room]
	i := slices.Index(here, item)
	if i < 0 {
		return fmt.Sprintf("There is no %s here.", item)
	}
	g.items[g.room] = slices.Delete(here, i, i+1)
	g.inventory = append(g.inventory, item)
	return fmt.Sprintf("Taken: %s.", item)
}

func (g *Game) drop(item string) string {
	if item == "" {
		return "Drop what?"
	}
	i := slices.Index(g.inventory, item)
	if i < 0 {
		return fmt.Sprintf("You don't have a %s.", item)
	}
	g.inventory = slices.Delete(g.inventory, i, i+1)
	g.items[g.room] = append(g.items[g.room], item)
	return fmt.Sprintf("Dropped: %s.", item)
}
