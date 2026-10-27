package adventure

import (
	"encoding/json"
	"fmt"
	"io"
)

type saveFile struct {
	Room      string              `json:"room"`
	Inventory []string            `json:"inventory"`
	Rooms     map[string][]string `json:"rooms"`
	Moves     int                 `json:"moves"`
	Won       bool                `json:"won"`
}

// Save writes the game's state (not the world) as JSON.
func (g *Game) Save(w io.Writer) error {
	state := saveFile{
		Room:      g.room,
		Inventory: append([]string{}, g.inventory...),
		Rooms:     g.items,
		Moves:     g.moves,
		Won:       g.won,
	}
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(state)
}

// LoadGame restores a saved game on top of its world; rooms missing from the save keep no items.
func LoadGame(w *World, r io.Reader) (*Game, error) {
	var state saveFile
	if err := json.NewDecoder(r).Decode(&state); err != nil {
		return nil, fmt.Errorf("save: %w", err)
	}
	if _, ok := w.Rooms[state.Room]; !ok {
		return nil, fmt.Errorf("save: unknown room %s", state.Room)
	}
	items := make(map[string][]string, len(w.Rooms))
	for name := range w.Rooms {
		items[name] = append([]string(nil), state.Rooms[name]...)
	}
	for name := range state.Rooms {
		if _, ok := w.Rooms[name]; !ok {
			return nil, fmt.Errorf("save: unknown room %s", name)
		}
	}
	return &Game{
		world:     w,
		room:      state.Room,
		inventory: append([]string(nil), state.Inventory...),
		items:     items,
		moves:     state.Moves,
		won:       state.Won,
	}, nil
}
