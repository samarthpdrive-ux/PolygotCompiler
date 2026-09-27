#include <iostream>

void increment(int& value) {
    value += 1;
}

int main() {
    int count = 4;
    increment(count);
    cout << count << endl;
    return 0;
}
