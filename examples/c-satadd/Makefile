CC ?= gcc
CFLAGS ?= -Wall -Wextra -O0

test: tests/test_satadd
	./tests/test_satadd

tests/test_satadd: tests/test_satadd.c src/satadd.c src/satadd.h
	$(CC) $(CFLAGS) -o $@ tests/test_satadd.c src/satadd.c

clean:
	rm -f tests/test_satadd
