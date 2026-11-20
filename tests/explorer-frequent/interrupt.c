/* The installed Explorer makes the real calls; this only holds them at test boundaries. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void mark(const char *path)
{
    int (*real_open)(const char *, int, ...) = dlsym(RTLD_NEXT, "open");
    int fd = real_open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, "1\n", 2) != 2 || close(fd))
        _exit(121);
}

static void hold(const char *path)
{
    const char *policy = getenv("W7_TEST_HOLD_POLICY");
    const char *arm = getenv("W7_TEST_HOLD_ARM");
    if (policy && arm && strcmp(path, policy) == 0 && access(arm, F_OK) == 0) {
        mark(getenv("W7_TEST_MARKER"));
        while (access(arm, F_OK) == 0)
            usleep(1000);
    }
}

#define WRAP_OPEN(name) \
int name(const char *path, int flags, ...) \
{ \
    int (*real)(const char *, int, ...) = dlsym(RTLD_NEXT, #name); \
    hold(path); \
    if (!(flags & O_CREAT) && (flags & O_TMPFILE) != O_TMPFILE) \
        return real(path, flags); \
    va_list args; \
    va_start(args, flags); \
    mode_t mode = va_arg(args, int); \
    va_end(args); \
    return real(path, flags, mode); \
}
WRAP_OPEN(open)
WRAP_OPEN(open64)

int fsync(int fd)
{
    int (*real)(int) = dlsym(RTLD_NEXT, "fsync");
    int result = real(fd);
    const char *state = getenv("W7_TEST_STOP_IN");
    if (!result && state) {
        char descriptor[64], target[4096];
        snprintf(descriptor, sizeof descriptor, "/proc/self/fd/%d", fd);
        ssize_t n = readlink(descriptor, target, sizeof target);
        size_t len = strlen(state);
        if (n > (ssize_t)len && !memcmp(target, state, len) && target[len] == '/') {
            mark(getenv("W7_TEST_MARKER"));
            raise(SIGSTOP);
        }
    }
    return result;
}
