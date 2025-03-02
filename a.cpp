#include <iostream>

// Rekurencyjna struktura szablonowa
template<int N>
struct CompileError {
    static_assert(N < 10, "Zbyt głęboka rekurencja szablonu!");
    using type = typename CompileError<N + 1>::type;
};

// Wywołanie rekurencyjne
int main() {
    CompileError<0>::type obj;
    return 0;
}
