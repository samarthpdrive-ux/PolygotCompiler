#include <iostream>

int main() {
    // Lightweight evaluator collection facade: vector<T> with add/length.
    vector<int> scores = new vector();
    scores.add(82);
    scores.add(91);

    int total = 0;
    for (int score : scores) {
        total += score;
    }

    cout << "Total:" << total << endl;
    return 0;
}
