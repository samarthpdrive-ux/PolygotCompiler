public class complete_java_main {
    public static void main(String[] args) {
        int items[] = {1, 2, 3, 4, 5};
        int total = 0;

        for (int index = 0; index < items.length(); index++) {
            total += items[index];
        }

        print(total);
    }
}
