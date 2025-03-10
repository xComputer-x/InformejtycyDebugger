#include<bits/stdc++.h>
using namespace std;

struct InternetUser {
	uint32_t idx;
	string full_name; 
	char* login;
	uint8_t age;
	uint8_t creation_time_epoch;
} root;

int main()
{
	unsigned int student_count;
	cout << "Enter number of students: ";
	cin >> student_count;

	vector<InternetUser> users(student_count);

	string temp_login;
	for (unsigned int i=0; i<student_count; i++) {
		cout << "Student no " << i << endl;
		users[i].idx = i;

		cin.ignore();
		cout << "\tFull name: ";
		getline(cin, users[i].full_name);

		cout << "\tLogin: ";
		cin >> temp_login;
		users[i].login = (char*)malloc(temp_login.size()+1);
		memcpy(users[i].login, temp_login.c_str(), temp_login.size()+1);

		cout << "\tAge: ";
		cin >> users[i].age;

		users[i].creation_time_epoch = time(nullptr);
	}

	for (InternetUser u : users) {
		free(u.login);
	}
}
