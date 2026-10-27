package library;

public final class Member {
    private final String id;
    private final String name;
    private int finesCents;

    public Member(String id, String name, int finesCents) {
        this.id = id;
        this.name = name;
        this.finesCents = finesCents;
    }

    public String id() {
        return id;
    }

    public String name() {
        return name;
    }

    public int finesCents() {
        return finesCents;
    }

    void addFine(int cents) {
        finesCents += cents;
    }

    void pay(int cents) {
        if (cents <= 0 || cents > finesCents) {
            throw new IllegalArgumentException("payment must be between 1 and " + finesCents);
        }
        finesCents -= cents;
    }
}
