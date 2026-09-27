class Counter { int value = 0; void increment(int amount) { this.value = this.value + amount; } }
Counter counter = new Counter();
counter.increment(7);
result = counter.value;
print(result);
