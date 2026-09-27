public class matrix_java {
    public static void main(String[] args) {
        int matrix[] = {{1, 2, 3}, {4, 5, 6}};
        int total = 0;

        for (int row : matrix) {
            for (int value : row) {
                total += value;
            }
        }

        print(matrix[1][2]);
        print(total);
    }
}
