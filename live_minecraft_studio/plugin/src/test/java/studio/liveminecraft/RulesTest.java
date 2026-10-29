package studio.liveminecraft;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RulesTest {
    @Test void frameHasFloorAndWallsButNoRoof() {
        Bounds b = new Bounds(77, 76, 130, 9, 9, 12);
        assertTrue(b.frame(77, 75, 130));
        assertTrue(b.frame(76, 87, 135));
        assertFalse(b.frame(80, 88, 135));
        assertFalse(b.frame(76, 88, 135));
        assertTrue(b.inside(85, 87, 138));
        assertFalse(b.inside(85, 88, 138));
        for (int i = 0; i < b.capacity(); i++) assertEquals(i, b.index(b.px(i), b.py(i), b.pz(i)));
    }
    @Test void manualFillCanWinWithoutAnyGift() {
        Round r = new Round();
        assertFalse(r.tick(0, true, 10, true));
        assertFalse(r.tick(199, true, 10, true));
        assertTrue(r.tick(200, true, 10, true));
        assertFalse(r.tick(400, true, 10, true));
    }
    @Test void breakingAndRefillingInSameTickRestartsWholeCountdown() {
        Round r = new Round();
        r.tick(0, true, 10, true);
        r.lostBlock();
        assertFalse(r.tick(199, true, 10, true));
        assertFalse(r.tick(200, true, 10, true));
        assertTrue(r.tick(399, true, 10, true));
    }
    @Test void worldVerificationRequiredBeforeWin() {
        Round r = new Round();
        r.tick(0, true, 1, true);
        assertFalse(r.tick(20, true, 1, false));
        assertTrue(r.tick(21, true, 1, true));
    }
    @Test void giftChangesRemainingCountdown() {
        Round r = new Round();
        r.tick(0, true, 10, true);
        r.change(20, 5, false);
        assertEquals(14, r.remaining(20));
        r.change(20, 3, true);
        assertEquals(3, r.remaining(20));
        assertTrue(r.tick(80, true, 10, true));
    }
}
