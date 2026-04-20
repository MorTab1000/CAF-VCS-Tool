#ifndef COMMIT_H
#define COMMIT_H

#include <string>
#include <cstdint>
#include <optional>
#include <vector>

class Commit {
public:
    const std::string tree_hash;  // Hash of the tree object
    const std::string author;     // Author of the commit
    const std::string message;    // Commit message
    const std::int64_t timestamp;  // Timestamp of the commit
    const std::vector<std::string> parents; // Parents commit hash

    Commit(const std::string& tree_hash, const std::string& author, const std::string& message, std::int64_t timestamp, std::vector<std::string> parents = {}):
            tree_hash(tree_hash), author(author), message(message), timestamp(timestamp), parents(parents) {}
};

#endif // COMMIT_H
