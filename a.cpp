#include<iostream>
using namespace std;

struct Mystruct {
	int smth;
	float b;
	void* c;
};

void dosmth(Mystruct& a)
{
	cout << a.smth << endl;
}

int main()
{
	Mystruct d;
	d.smth = 1;
	d.b = 0.1;
	d.c = nullptr;

	dosmth(d);
}
