public class static_java {
    public static void main(String[] args) {
        Counter.add(4);
        Counter.add(3);
        System.out.println(Counter.total);
    }
}

class Counter {
    static int total = 0;

    static void add(int value) {
        Counter.total += value;
    }
}
