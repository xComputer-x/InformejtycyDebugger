#include<iostream>
#include<vector>
using namespace std;

vector<unsigned int> hello(vector<unsigned int> a, unsigned int b)
{
	a[0]*=b;
  	return a;
}

int main()
{
	vector<unsigned> a;
  	hello(a, 5);
}
