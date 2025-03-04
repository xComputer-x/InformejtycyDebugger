#include<iostream>
using namespace std;

int e()
{
	return 0;
}

void c(void* d)
{
	return;
}

int main()
{
    int a, b;
	c(&a);
    cin >> a >> b;
    cout << a / b << endl;
}
