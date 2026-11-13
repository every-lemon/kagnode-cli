package main

import (
	"errors"
	"os"
	"path/filepath"
	"sync"
	"syscall"
)

// Serialize cooperative credential transactions across CLI processes. Keep this
// stable control inode after logout; removing lock files can split ownership.
func credentialLock() (func(), error) {
	directory := pathFor("config")
	if err := ensureDir(directory); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(filepath.Join(directory, ".account.lock"), os.O_RDWR|os.O_CREATE|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0600)
	if err != nil {
		return nil, errors.New("account control is unavailable or unsafe")
	}
	info, err := file.Stat()
	if err != nil {
		file.Close()
		return nil, err
	}
	owner, ok := info.Sys().(*syscall.Stat_t)
	if !info.Mode().IsRegular() || !ok || owner.Uid != uint32(os.Geteuid()) || owner.Nlink != 1 || info.Mode().Perm()&0077 != 0 {
		file.Close()
		return nil, errors.New("account control must be a private single-link regular file owned by the current user")
	}
	if err = syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		file.Close()
		return nil, errors.New("another account operation is in progress; retry after it finishes")
	}
	var once sync.Once
	return func() { once.Do(func() { _ = syscall.Flock(int(file.Fd()), syscall.LOCK_UN); _ = file.Close() }) }, nil
}
