#include <iostream>

int fibonacci(int value) {
    if (value <= 1) {
        return value;
    }
    return fibonacci(value - 1) + fibonacci(value - 2);
}

int main() {
    int result = fibonacci(7);
    print(result);
    return 0;
}
