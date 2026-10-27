package adventure

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

const worldJSON = `{
  "start": "hall",
  "goal": "vault",
  "rooms": {
    "hall":    {"description": "A dusty hall.", "exits": {"north": "library", "east": "kitchen"}, "items": ["lamp"]},
    "kitchen": {"description": "A cold kitchen.", "exits": {"west": "hall"}, "items": ["bread", "apple"]},
    "library": {"description": "Tall shelves.", "exits": {"south": "hall", "east": "vault"}, "items": ["key"]},
    "vault":   {"description": "Gold everywhere!", "exits": {"west": "library"}, "locked_by": "key"}
  }
}`

func newGame(t *testing.T) *Game {
	t.Helper()
	world, err := LoadWorld(strings.NewReader(worldJSON))
	if err != nil {
		t.Fatalf("LoadWorld: %v", err)
	}
	return NewGame(world)
}

func expect(t *testing.T, g *Game, command, want string) {
	t.Helper()
	if got := g.Do(command); got != want {
		t.Errorf("Do(%q):\n got %q\nwant %q", command, got, want)
	}
}

func TestLook(t *testing.T) {
	g := newGame(t)
	expect(t, g, "look", "A dusty hall.\nExits: east, north\nYou see: lamp")
	expect(t, g, "  L  ", "A dusty hall.\nExits: east, north\nYou see: lamp")
}

func TestMovingAndAliases(t *testing.T) {
	g := newGame(t)
	expect(t, g, "go east", "A cold kitchen.\nExits: west\nYou see: apple, bread")
	expect(t, g, "W", "A dusty hall.\nExits: east, north\nYou see: lamp")
	expect(t, g, "north", "Tall shelves.\nExits: east, south\nYou see: key")
	expect(t, g, "go up", "You can't go up.")
	expect(t, g, "go", "Go where?")
	if g.Room() != "library" || g.Moves() != 3 {
		t.Fatalf("room %s, moves %d", g.Room(), g.Moves())
	}
}

func TestItems(t *testing.T) {
	g := newGame(t)
	expect(t, g, "inventory", "You are carrying nothing.")
	expect(t, g, "take lamp", "Taken: lamp.")
	expect(t, g, "take lamp", "There is no lamp here.")
	expect(t, g, "look", "A dusty hall.\nExits: east, north")
	expect(t, g, "e", "A cold kitchen.\nExits: west\nYou see: apple, bread")
	expect(t, g, "get   BREAD", "Taken: bread.")
	expect(t, g, "i", "You are carrying: bread, lamp")
	expect(t, g, "drop lamp", "Dropped: lamp.")
	expect(t, g, "drop sword", "You don't have a sword.")
	expect(t, g, "take", "Take what?")
	expect(t, g, "look", "A cold kitchen.\nExits: west\nYou see: apple, lamp")
}

func TestLockedRoomAndWinning(t *testing.T) {
	g := newGame(t)
	g.Do("n")
	expect(t, g, "e", "The way east is locked. You need the key.")
	g.Do("take key")
	expect(t, g, "e", "Gold everywhere!\nExits: west\nYou win!")
	if !g.Won() {
		t.Fatal("expected a win")
	}
	expect(t, g, "look", "The game is over.")
}

func TestUnknownCommand(t *testing.T) {
	g := newGame(t)
	expect(t, g, "dance wildly", `I don't understand "dance wildly".`)
	expect(t, g, "", "Say something.")
}

func TestSaveAndLoad(t *testing.T) {
	g := newGame(t)
	g.Do("take lamp")
	g.Do("e")
	g.Do("take apple")
	var buf bytes.Buffer
	if err := g.Save(&buf); err != nil {
		t.Fatalf("Save: %v", err)
	}
	var raw map[string]any
	if err := json.Unmarshal(buf.Bytes(), &raw); err != nil {
		t.Fatalf("save is not JSON: %v", err)
	}
	for _, key := range []string{"room", "inventory", "rooms", "moves"} {
		if _, ok := raw[key]; !ok {
			t.Errorf("save lacks %q", key)
		}
	}
	world, _ := LoadWorld(strings.NewReader(worldJSON))
	restored, err := LoadGame(world, bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("LoadGame: %v", err)
	}
	if restored.Room() != "kitchen" || restored.Moves() != 1 {
		t.Fatalf("room %s moves %d", restored.Room(), restored.Moves())
	}
	expect(t, restored, "i", "You are carrying: apple, lamp")
	expect(t, restored, "look", "A cold kitchen.\nExits: west\nYou see: bread")
	expect(t, restored, "w", "A dusty hall.\nExits: east, north")
	// the original world value is not shared with the first game
	fresh := NewGame(world)
	expect(t, fresh, "look", "A dusty hall.\nExits: east, north\nYou see: lamp")
}

func TestLoadGameRejectsUnknownRoom(t *testing.T) {
	world, _ := LoadWorld(strings.NewReader(worldJSON))
	_, err := LoadGame(world, strings.NewReader(`{"room":"attic","inventory":[],"rooms":{},"moves":0}`))
	if err == nil || err.Error() != "save: unknown room attic" {
		t.Fatalf("got %v", err)
	}
}

func TestLoadWorldValidation(t *testing.T) {
	cases := map[string]string{
		`{"start":"a","rooms":{"a":{"description":"A","exits":{"up":"b"}}}}`: "room a: exit up leads to unknown room b",
		`{"start":"x","rooms":{"a":{"description":"A"}}}`:                     "start room x does not exist",
		`{"start":"a","goal":"z","rooms":{"a":{"description":"A"}}}`:          "goal room z does not exist",
		`not json`: "invalid world",
	}
	for src, want := range cases {
		_, err := LoadWorld(strings.NewReader(src))
		if err == nil || !strings.Contains(err.Error(), want) {
			t.Errorf("LoadWorld(%s): got %v, want %q", src, err, want)
		}
	}
}
