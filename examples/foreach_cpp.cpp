#include <iostream>

int main() {
    int values[] = {4, 7, 9};
    int total = 0;

    for (int value : values) {
        total += value;
    }

    print(total);
    return 0;
}
