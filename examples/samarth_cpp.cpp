#include <iostream>

int main() {
    // Array literal syntax: the parser reads the expressions inside { ... }.
    int items[] = {1, 2, 3, 4, 5};
    int target = 5;
    int multiplier = 3;
    int runningTotal = 0;
    int matchCount = 0;

    for (int i = 0; i < items.length(); i++) {
        int current = items[i];
        if (current == target) {
            matchCount++;
            runningTotal += current * multiplier;
        } else {
            runningTotal += current;
        }
    }

    if (matchCount > 0) {
        runningTotal -= 10;
    } else {
        runningTotal += 10;
    }

    print(matchCount);   // Expected: 1
    print(runningTotal); // Expected: 15
    return 0;
}
