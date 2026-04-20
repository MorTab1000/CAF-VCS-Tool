#include <string>
#include <unistd.h>
#include <fcntl.h>
#include <sys/file.h>
#include <vector>
#include <cstring>
#include <stdexcept>
#include <map>

#include "caf.h"
#include "object_io.h"
#include "hash_types.h"

// Maximum string length for length-prefixed strings
constexpr uint32_t MAX_LENGTH = 1024 * 1024;  // 1 MB limit for strings
constexpr uint32_t MAX_PARENTS = 65536;  // Maximum number of parent commits to prevent excessive memory usage
constexpr uint32_t MAX_RECORDS = 1048576;     // 1 million files max per directory

namespace {
    // RAII wrapper for safe file descriptor management
    struct ScopedFileLock {
        int fd;
        
        explicit ScopedFileLock(int fd) : fd(fd) {}
        
        ~ScopedFileLock() {
            if (fd >= 0) {
                flock(fd, LOCK_UN);
                close(fd);
            }
        }
        
        // Delete copy operations to prevent double-closing
        ScopedFileLock(const ScopedFileLock&) = delete;
        ScopedFileLock& operator=(const ScopedFileLock&) = delete;
    };
    void read_exact(int fd, uint8_t* buffer, size_t length); // Helper function to read exact number of bytes
    void write_exact(int fd, const uint8_t* buffer, size_t length); // Helper function to write exact number of bytes
    uint32_t read_u32_le(int fd); // Helper function to read uint32 in little-endian order
    int64_t read_i64_le(int fd); // Helper function to read int64 in little-endian order
    void write_u32_le(int fd, uint32_t value); // Helper function to write uint32 in little-endian order
    void write_i64_le(int fd, int64_t value); // Helper function to write int64 in little-endian order
    std::string read_length_prefixed_string(int fd); // Helper function to read a length-prefixed string safely
    void write_with_length(int fd, const std::string &data); // Helper function to write a length-prefixed string safely
    void save_tree_record(int fd, const TreeRecord &record); // Helper function to serialize a TreeRecord
    TreeRecord load_tree_record(int fd); // Helper function to deserialize a TreeRecord
}   
// Serialize Commit to disk
void save_commit(const std::string &root_dir, const Commit &commit) {
    std::string commit_hash = hash_object(commit);
    int fd = open_content_for_writing(root_dir, commit_hash);

    try {
        ScopedFileLock file_guard(fd);

        write_with_length(fd, commit.tree_hash);
        write_with_length(fd, commit.author);
        write_with_length(fd, commit.message);

        write_i64_le(fd, static_cast<int64_t>(commit.timestamp));

        if (commit.parents.size() > MAX_PARENTS) {
            throw std::runtime_error("Number of parents exceeds maximum allowed limit");
        }

        uint32_t num_parents = static_cast<uint32_t>(commit.parents.size());
        write_u32_le(fd, num_parents);
        for (const auto &parent_hash : commit.parents) {
            write_with_length(fd, parent_hash);
        }

    } catch (const std::exception &e) {
        delete_content(root_dir, commit_hash);
        throw;
    }
}

// Deserialize Commit from disk
Commit load_commit(const std::string &root_dir, const std::string &commit_hash) {
    int fd = open_content_for_reading(root_dir, commit_hash);
    ScopedFileLock file_guard(fd);

    std::string tree_hash = read_length_prefixed_string(fd);
    std::string author = read_length_prefixed_string(fd);
    std::string message = read_length_prefixed_string(fd);

    int64_t timestamp = read_i64_le(fd);

    uint32_t num_parents = read_u32_le(fd);
    if (num_parents > MAX_PARENTS) {
            throw std::runtime_error("Number of parents exceeds maximum allowed limit");
        }
    
    
    std::vector<std::string> parents;
    parents.reserve(num_parents);

    for (uint32_t i = 0; i < num_parents; ++i) {
        parents.push_back(read_length_prefixed_string(fd));
    }
    
    return Commit(tree_hash, author, message, timestamp, parents);
}

void save_tree(const std::string &root_dir, const Tree &tree) {
    std::string tree_hash = hash_object(tree);

    int fd = open_content_for_writing(root_dir, tree_hash);

     try {
        ScopedFileLock file_guard(fd);
        if (tree.records.size() > MAX_RECORDS) {
            throw std::runtime_error("Number of tree records exceeds maximum allowed limit");
        }

        uint32_t num_records = static_cast<uint32_t>(tree.records.size());
        write_u32_le(fd, num_records);

        for (const auto &[name, record] : tree.records) {
            save_tree_record(fd, record);
        }


    } catch (const std::exception &e) {
        delete_content(root_dir, tree_hash);
        throw;
    }
}

Tree load_tree(const std::string &root_dir, const std::string &tree_hash) {
    int fd = open_content_for_reading(root_dir, tree_hash);
    ScopedFileLock file_guard(fd);
    uint32_t num_records = read_u32_le(fd);

    if (num_records > MAX_RECORDS) {
        throw std::runtime_error("Number of tree records exceeds maximum allowed limit");
    }

    std::map<std::string, TreeRecord> records;
    for (uint32_t i = 0; i < num_records; ++i) {
        TreeRecord record = load_tree_record(fd);
        records.emplace(record.name, record);
    }

    return Tree(records);
}

namespace { 
    void read_exact(int fd, uint8_t* buffer, size_t length) {
        size_t bytes_read = 0;
        while (bytes_read < length) {
            ssize_t result = read(fd, buffer + bytes_read, length - bytes_read);
            if (result < 0) {
                if (errno == EINTR) continue; // Interrupted by signal, try again
                throw std::runtime_error("System error during read");
            }
            if (result == 0) {
                throw std::runtime_error("Unexpected EOF while reading object");
            }
            bytes_read += result;
        }
    }

    void write_exact(int fd, const uint8_t* buffer, size_t length) {
        size_t bytes_written = 0;
        while (bytes_written < length) {
            ssize_t result = write(fd, buffer + bytes_written, length - bytes_written);
            if (result < 0) {
                if (errno == EINTR) continue; // Interrupted by signal, try again
                throw std::runtime_error("System error during write");
            }

            if (result == 0) {
                throw std::runtime_error("Failed to make forward progress during write (possible disk full)");
            }

            bytes_written += result;
        }
    }

    uint32_t read_u32_le(int fd) {
        uint8_t bytes[4];
        read_exact(fd, bytes, sizeof(bytes));

        return static_cast<uint32_t>(bytes[0]) |
            (static_cast<uint32_t>(bytes[1]) << 8) |
            (static_cast<uint32_t>(bytes[2]) << 16) |
            (static_cast<uint32_t>(bytes[3]) << 24);
    }

    int64_t read_i64_le(int fd) {
        uint8_t bytes[8];
        read_exact(fd, bytes, sizeof(bytes));

        uint64_t value = static_cast<uint64_t>(bytes[0]) |
                        (static_cast<uint64_t>(bytes[1]) << 8) |
                        (static_cast<uint64_t>(bytes[2]) << 16) |
                        (static_cast<uint64_t>(bytes[3]) << 24) |
                        (static_cast<uint64_t>(bytes[4]) << 32) |
                        (static_cast<uint64_t>(bytes[5]) << 40) |
                        (static_cast<uint64_t>(bytes[6]) << 48) |
                        (static_cast<uint64_t>(bytes[7]) << 56);

        return static_cast<int64_t>(value);
    }

    void write_u32_le(int fd, uint32_t value) {
        uint8_t bytes[4] = {
            static_cast<uint8_t>(value & 0xFF),
            static_cast<uint8_t>((value >> 8) & 0xFF),
            static_cast<uint8_t>((value >> 16) & 0xFF),
            static_cast<uint8_t>((value >> 24) & 0xFF),
        };

        write_exact(fd, bytes, sizeof(bytes));
    }

    void write_i64_le(int fd, int64_t value) {
        uint64_t uvalue = static_cast<uint64_t>(value);
        uint8_t bytes[8] = {
            static_cast<uint8_t>(uvalue & 0xFF),
            static_cast<uint8_t>((uvalue >> 8) & 0xFF),
            static_cast<uint8_t>((uvalue >> 16) & 0xFF),
            static_cast<uint8_t>((uvalue >> 24) & 0xFF),
            static_cast<uint8_t>((uvalue >> 32) & 0xFF),
            static_cast<uint8_t>((uvalue >> 40) & 0xFF),
            static_cast<uint8_t>((uvalue >> 48) & 0xFF),
            static_cast<uint8_t>((uvalue >> 56) & 0xFF),
        };

        write_exact(fd, bytes, sizeof(bytes));
    }

    std::string read_length_prefixed_string(int fd) {
        uint32_t length = read_u32_le(fd);

        if (length == 0) {
            return "";
        }

        if (length > MAX_LENGTH)
            throw std::runtime_error("Length exceeds maximum");

        std::string result(length, '\0');

        read_exact(fd, reinterpret_cast<uint8_t*>(&result[0]), length);
        return result;
    }

    void write_with_length(int fd, const std::string &data) {
        if (data.length() > MAX_LENGTH) {
            throw std::runtime_error("String length exceeds maximum allowed size");
        }

        uint32_t length = data.length();
        write_u32_le(fd, length);

        if (length == 0) {
            return;
        }

        write_exact(fd, reinterpret_cast<const uint8_t*>(data.c_str()), length);
    }

    void save_tree_record(int fd, const TreeRecord &record) {
        uint8_t type = static_cast<uint8_t>(record.type);
        write_exact(fd, &type, sizeof(type));

        write_with_length(fd, record.hash);
        write_with_length(fd, record.name);
    }

    TreeRecord load_tree_record(int fd) {
        uint8_t type;

        read_exact(fd, &type, sizeof(type));

        TreeRecord::Type record_type = static_cast<TreeRecord::Type>(type);
        std::string hash = read_length_prefixed_string(fd);
        std::string name = read_length_prefixed_string(fd);

        return TreeRecord(record_type, hash, name);
    }
}