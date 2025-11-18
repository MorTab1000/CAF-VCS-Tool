#ifndef TAG_H
#define TAG_H

#include <string>

class Tag {
public:
    const std::string commit_hash;
    const std::string name;

    Tag(const std::string& commit_hash, const std::string& name):
        commit_hash(commit_hash), name(name) {}
};

#endif // TAG_H