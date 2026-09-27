#include <iostream>

int main() {
    int matrix[] = {{1, 2, 3}, {4, 5, 6}};
    int total = 0;

    for (int row : matrix) {
        for (int value : row) {
            total += value;
        }
    }

    print(matrix[1][2]);
    print(total);
    return 0;
}
