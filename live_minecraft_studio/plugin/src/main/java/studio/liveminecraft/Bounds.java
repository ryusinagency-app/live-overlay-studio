package studio.liveminecraft;

record Bounds(int x, int y, int z, int width, int depth, int height) {
    int capacity() { return width * depth * height; }
    int px(int i) { return x + i % width; }
    int py(int i) { return y + i / (width * depth); }
    int pz(int i) { return z + i / width % depth; }
    boolean inside(int bx, int by, int bz) {
        return bx >= x && bx < x + width && by >= y && by < y + height && bz >= z && bz < z + depth;
    }
    int index(int bx, int by, int bz) { return ((by - y) * depth + bz - z) * width + bx - x; }
    boolean frame(int bx, int by, int bz) {
        if (bx < x - 1 || bx > x + width || bz < z - 1 || bz > z + depth || by < y - 1 || by >= y + height) return false;
        return by == y - 1 || bx == x - 1 || bx == x + width || bz == z - 1 || bz == z + depth;
    }
}
