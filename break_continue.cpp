#include <iostream>

int main() {
    for (int number = 1; number < 10; number++) {
        if (number == 5) {
            continue;
        }

        if (number == 8) {
            break;
        }

        std::cout << number << std::endl;
    }

    return 0;
}