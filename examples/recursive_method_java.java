public class recursive_method_java {
    int countdown(int value) {
        if (value <= 0) {
            return 0;
        }
        return 1 + countdown(value - 1);
    }

    public static void main(String[] args) {
        recursive_method_java program = new recursive_method_java();
        int result = program.countdown(5);
        print(result);
    }
}
