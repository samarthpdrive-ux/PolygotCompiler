File file = open("student.txt", "w");
file.write("Name: Samarth\nAge: 24");
file.close();

File reader = open("student.txt", "r");
contents = reader.read();
reader.close();
print(contents);
