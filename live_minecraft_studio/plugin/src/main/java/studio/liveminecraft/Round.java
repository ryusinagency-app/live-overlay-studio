package studio.liveminecraft;

/** Server-tick countdown. A loss invalidates the countdown even if refilled that tick. */
final class Round {
    private long deadline = -1;
    private boolean won = false;
    void lostBlock() { deadline = -1; won = false; }
    void reset() { lostBlock(); }
    long remaining(long tick) { return deadline < 0 ? 0 : Math.max(0, (deadline - tick + 19) / 20); }
    boolean counting() { return deadline >= 0 && !won; }
    void change(long tick, int seconds, boolean set) {
        if (counting()) deadline = set ? tick + Math.max(0, seconds) * 20L : Math.max(tick, deadline + seconds * 20L);
    }
    void rebase(long tick, int oldSeconds, int newSeconds) {
        if (counting()) deadline = Math.max(tick, deadline + (newSeconds - oldSeconds) * 20L);
    }
    boolean tick(long tick, boolean full, int holdSeconds, boolean verified) {
        if (!full) { lostBlock(); return false; }
        if (won) return false;
        if (deadline < 0) deadline = tick + holdSeconds * 20L;
        if (tick < deadline || !verified) return false;
        won = true;
        return true;
    }
}
