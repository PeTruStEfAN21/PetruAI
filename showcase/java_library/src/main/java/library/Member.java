package library;

public record Member(String id, String name, int finesCents) {
    public Member {
        if (finesCents < 0) finesCents = 0;
    }
}
