package adventure

import (
	"encoding/json"
	"fmt"
	"io"
	"sort"
)

// Room is one location of the world as the JSON file describes it.
type Room struct {
	Description string            `json:"description"`
	Exits       map[string]string `json:"exits"`
	Items       []string          `json:"items"`
	LockedBy    string            `json:"locked_by"`
}

// World is the static map; a Game never changes it.
type World struct {
	Start string          `json:"start"`
	Goal  string          `json:"goal"`
	Rooms map[string]Room `json:"rooms"`
}

func LoadWorld(r io.Reader) (*World, error) {
	var w World
	if err := json.NewDecoder(r).Decode(&w); err != nil {
		return nil, fmt.Errorf("invalid world: %w", err)
	}
	if err := w.validate(); err != nil {
		return nil, err
	}
	return &w, nil
}

func (w *World) validate() error {
	if _, ok := w.Rooms[w.Start]; !ok {
		return fmt.Errorf("start room %s does not exist", w.Start)
	}
	if w.Goal != "" {
		if _, ok := w.Rooms[w.Goal]; !ok {
			return fmt.Errorf("goal room %s does not exist", w.Goal)
		}
	}
	for _, name := range sortedKeys(w.Rooms) {
		room := w.Rooms[name]
		for _, dir := range sortedKeys(room.Exits) {
			if _, ok := w.Rooms[room.Exits[dir]]; !ok {
				return fmt.Errorf("room %s: exit %s leads to unknown room %s", name, dir, room.Exits[dir])
			}
		}
	}
	return nil
}

// initialItems is a fresh copy of every room's items, so games never share state with the world.
func (w *World) initialItems() map[string][]string {
	items := make(map[string][]string, len(w.Rooms))
	for name, room := range w.Rooms {
		items[name] = append([]string(nil), room.Items...)
	}
	return items
}

func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
