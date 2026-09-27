int marks[3] = {70, 82, 91};
marks[0] = 75;
int total = 0;
for (int index = 0; index < 3; index = index + 1) {
    total = total + marks[index];
}
print(total);
print(marks[0]);
