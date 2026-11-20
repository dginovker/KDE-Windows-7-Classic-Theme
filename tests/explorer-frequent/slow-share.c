#define FUSE_USE_VERSION 31
#include <fuse3/fuse.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <unistd.h>

static const char policy[] = "[Plugin-org.kde.ActivityManager.Resources.Scoring]\nwhat-to-remember=2\n";
static const char policyPath[] = "/kactivitymanagerd-pluginsrc";

// The real VFS request stays pending while the harness drives input into Plasma.
static void hold(const char *gate, const char *pending)
{
    if (access(gate, F_OK) != 0)
        return;
    int fd = open(pending, O_CREAT | O_WRONLY, 0600);
    if (fd >= 0)
        close(fd);
    for (int i = 0; i < 3000 && access(gate, F_OK) == 0; ++i)
        usleep(10000);
    unlink(pending);
}

static int attributes(const char *path, struct stat *st, struct fuse_file_info *fi)
{
    (void)fi;
    if (!strcmp(path, policyPath)) {
        hold("/home/tester/w7f35/policy-slow", "/home/tester/w7f35/policy-pending");
        st->st_mode = S_IFREG | 0444;
        st->st_size = sizeof policy - 1;
        st->st_nlink = 1;
        return 0;
    }
    if (!strcmp(path, "/Projects") || !strcmp(path, "/frequent.json"))
        hold("/home/tester/w7f35/slow", "/home/tester/w7f35/pending");
    if (strcmp(path, "/") && strcmp(path, "/Projects") && strcmp(path, "/Other") && strcmp(path, "/Listing"))
        return -ENOENT;
    st->st_mode = S_IFDIR | 0700;
    st->st_uid = getuid();
    st->st_gid = getgid();
    st->st_nlink = 2;
    return 0;
}

static int openPolicy(const char *path, struct fuse_file_info *info)
{
    if (strcmp(path, policyPath))
        return -ENOENT;
    return (info->flags & O_ACCMODE) == O_RDONLY ? 0 : -EACCES;
}

static int readPolicy(const char *path, char *buf, size_t len, off_t off, struct fuse_file_info *info)
{
    (void)info;
    if (strcmp(path, policyPath))
        return -ENOENT;
    const size_t size = sizeof policy - 1;
    if ((size_t)off >= size)
        return 0;
    if (len > size - (size_t)off)
        len = size - (size_t)off;
    memcpy(buf, policy + off, len);
    return len;
}

static int entries(const char *path, void *buf, fuse_fill_dir_t fill, off_t off,
                   struct fuse_file_info *info, enum fuse_readdir_flags flags)
{
    (void)off; (void)info; (void)flags;
    if (!strcmp(path, "/Listing"))
        hold("/home/tester/w7f35/listing-slow", "/home/tester/w7f35/listing-pending");
    fill(buf, ".", NULL, 0, 0);
    fill(buf, "..", NULL, 0, 0);
    if (!strcmp(path, "/")) {
        fill(buf, "Projects", NULL, 0, 0);
        fill(buf, "Other", NULL, 0, 0);
    }
    return 0;
}

int main(int argc, char **argv)
{
    const struct fuse_operations ops = {.getattr = attributes, .readdir = entries, .open = openPolicy, .read = readPolicy};
    return fuse_main(argc, argv, &ops, NULL);
}
