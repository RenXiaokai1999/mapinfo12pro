"""Position-independent x86 hooks for the Build 208 native table undo list."""

from collections import namedtuple


FREE_LIST = 0x144750
REGISTER_UNDO = 0x147740
APPLY_UNDO = 0x1477C0
CLEAR_UNDO = 0x1473D0
PREPARE_UNDO = 0x791C0
READ_PREFERENCE = 0x307FA0
UNDO_GLOBALS = 0x671D90
LIST_OFFSET = 0x61C
CAPACITY = 32
ENTRY_SIZE = 28
RECORDS = 16
UNDO_OBJECT_LIMIT = 800

OWNER = 0
DEPTH = 4
APPLIED = 8
REPLAYING = 12

CallHook = namedtuple("CallHook", "site original replacement")


def build_history(base, slot, assemble):
    code = bytearray()

    def emit(source, *, frame=True, tail=None):
        address = base + len(code)
        # EBX is the actual image base, including when the DLL was relocated.
        entry = f"""
            push ebp
            mov ebp, esp
            push ebx
            push esi
            push edi
            call image_address
        image_address:
            pop ebx
            sub ebx, {(address + 11) & 0xffffffff:#x}
        """ if frame else ""
        leave = """
        done:
            lea esp, [ebp - 12]
            pop edi
            pop esi
            pop ebx
            pop ebp
        """ if frame else ""
        transfer = f"jmp {tail:#x}" if tail is not None else "ret"
        code.extend(assemble(entry + source + leave + transfer, address))
        return address

    # Release detached lists with the original owner while that owner is live.
    # The caller owns the active table list, which is restored before returning.
    release_all = emit(f"""
        mov esi, dword ptr [ebp + 8]
        test esi, esi
        je done
        mov edi, dword ptr [esi + {OWNER}]
        test edi, edi
        je reset
        sub esp, 8
        mov eax, dword ptr [edi + {LIST_OFFSET}]
        mov dword ptr [esp], eax
        mov eax, dword ptr [edi + {LIST_OFFSET + 4}]
        mov dword ptr [esp + 4], eax
    release_next:
        mov eax, dword ptr [esi + {DEPTH}]
        test eax, eax
        je restore_active
        dec eax
        mov dword ptr [esi + {DEPTH}], eax
        imul eax, {ENTRY_SIZE}
        mov ecx, dword ptr [esi + eax + {RECORDS}]
        mov dword ptr [edi + {LIST_OFFSET}], ecx
        mov ecx, dword ptr [esi + eax + {RECORDS + 4}]
        mov dword ptr [edi + {LIST_OFFSET + 4}], ecx
        push edi
        call {FREE_LIST:#x}
        add esp, 4
        jmp release_next
    restore_active:
        mov eax, dword ptr [esp]
        mov dword ptr [edi + {LIST_OFFSET}], eax
        mov eax, dword ptr [esp + 4]
        mov dword ptr [edi + {LIST_OFFSET + 4}], eax
    reset:
        mov dword ptr [esi + {OWNER}], 0
        mov dword ptr [esi + {DEPTH}], 0
        mov dword ptr [esi + {APPLIED}], 0
    """)

    capture = emit(f"""
        mov esi, dword ptr [ebx + {slot:#x}]
        test esi, esi
        je done
        cmp dword ptr [esi + {REPLAYING}], 0
        jne done
        cmp dword ptr [esi + {APPLIED}], 0
        jne done
        mov edi, dword ptr [ebp + 8]
        cmp dword ptr [esi + {OWNER}], edi
        jne done
        cmp dword ptr [ebx + {UNDO_GLOBALS:#x}], edi
        jne done
        cmp dword ptr [edi + {LIST_OFFSET}], 0
        je done
        cmp dword ptr [esi + {DEPTH}], {CAPACITY}
        jb store
        push dword ptr [edi + {LIST_OFFSET + 4}]
        push dword ptr [edi + {LIST_OFFSET}]
        mov eax, dword ptr [esi + {RECORDS}]
        mov dword ptr [edi + {LIST_OFFSET}], eax
        mov eax, dword ptr [esi + {RECORDS + 4}]
        mov dword ptr [edi + {LIST_OFFSET + 4}], eax
        push edi
        call {FREE_LIST:#x}
        add esp, 4
        pop dword ptr [edi + {LIST_OFFSET}]
        pop dword ptr [edi + {LIST_OFFSET + 4}]
        push esi
        push edi
        lea edi, [esi + {RECORDS}]
        lea esi, [edi + {ENTRY_SIZE}]
        mov ecx, {(CAPACITY - 1) * ENTRY_SIZE // 4}
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop edi
        pop esi
        dec dword ptr [esi + {DEPTH}]
    store:
        mov eax, dword ptr [esi + {DEPTH}]
        imul eax, {ENTRY_SIZE}
        lea edx, [esi + eax + {RECORDS}]
        mov eax, dword ptr [edi + {LIST_OFFSET}]
        mov dword ptr [edx], eax
        mov eax, dword ptr [edi + {LIST_OFFSET + 4}]
        mov dword ptr [edx + 4], eax
        mov dword ptr [edi + {LIST_OFFSET}], 0
        mov dword ptr [edi + {LIST_OFFSET + 4}], 0
        inc dword ptr [esi + {DEPTH}]
        lea esi, [ebx + {UNDO_GLOBALS:#x}]
        lea edi, [edx + 8]
        mov ecx, 4
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        mov ax, word ptr [esi]
        mov word ptr [edi], ax
    """, tail=FREE_LIST)

    cleanup = emit(f"""
        mov esi, dword ptr [ebx + {slot:#x}]
        test esi, esi
        je done
        cmp dword ptr [esi + {REPLAYING}], 0
        jne done
        mov eax, dword ptr [ebp + 8]
        cmp dword ptr [esi + {OWNER}], eax
        jne done
        push esi
        call {release_all:#x}
        add esp, 4
    """, tail=FREE_LIST)

    register = emit(f"""
        mov esi, dword ptr [ebx + {slot:#x}]
        test esi, esi
        jne ready
        push 4
        push 0x3000
        push 0x1000
        push 0
        call dword ptr [ebx + 0x535210]
        test eax, eax
        je done
        mov dword ptr [ebx + {slot:#x}], eax
        mov esi, eax
    ready:
        cmp dword ptr [esi + {REPLAYING}], 0
        jne done
        mov edi, dword ptr [ebp + 12]
        cmp dword ptr [esi + {OWNER}], edi
        je set_current
        push esi
        call {release_all:#x}
        add esp, 4
    set_current:
        mov dword ptr [esi + {OWNER}], edi
        mov dword ptr [esi + {APPLIED}], 0
    """, tail=REGISTER_UNDO)

    select_previous = emit(f"""
        mov esi, dword ptr [ebx + {slot:#x}]
        test esi, esi
        je done
        cmp dword ptr [esi + {APPLIED}], 0
        je done
        mov edi, dword ptr [esi + {OWNER}]
        cmp dword ptr [ebx + {UNDO_GLOBALS:#x}], edi
        jne done
        mov dword ptr [esi + {APPLIED}], 0
        cmp dword ptr [esi + {DEPTH}], 0
        jne previous
        push 0
        call {CLEAR_UNDO:#x}
        add esp, 4
        jmp done
    previous:
        push edi
        call {FREE_LIST:#x}
        add esp, 4
        dec dword ptr [esi + {DEPTH}]
        mov eax, dword ptr [esi + {DEPTH}]
        imul eax, {ENTRY_SIZE}
        lea esi, [esi + eax + {RECORDS}]
        mov eax, dword ptr [esi]
        mov dword ptr [edi + {LIST_OFFSET}], eax
        mov eax, dword ptr [esi + 4]
        mov dword ptr [edi + {LIST_OFFSET + 4}], eax
        add esi, 8
        lea edi, [ebx + {UNDO_GLOBALS:#x}]
        mov ecx, 4
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        mov ax, word ptr [esi]
        mov word ptr [edi], ax
    """)

    prepare = emit(f"call {select_previous:#x}\n", frame=False, tail=PREPARE_UNDO)

    # The graphical Edit command can go straight to apply, while the
    # MapBasic command also passes through prepare. Selection is idempotent.
    apply = emit(f"""
        mov esi, dword ptr [ebx + {slot:#x}]
        test esi, esi
        je apply_original
        cmp dword ptr [esi + {REPLAYING}], 0
        jne replay
        call {select_previous:#x}
    replay:
        inc dword ptr [esi + {REPLAYING}]
        call {APPLY_UNDO:#x}
        dec dword ptr [esi + {REPLAYING}]
        cmp ax, 1
        jne done
        mov edx, dword ptr [ebx + {UNDO_GLOBALS:#x}]
        cmp dword ptr [esi + {OWNER}], edx
        jne done
        mov dword ptr [esi + {APPLIED}], 1
        push eax
        mov edx, dword ptr [esi + {DEPTH}]
        test edx, edx
        jne label_previous
        push 0x833
        call 0x41d860
        add esp, 4
        push eax
        push 201
        call 0x284270
        add esp, 8
        push 0
        jmp update_enabled
    label_previous:
        dec edx
        imul edx, {ENTRY_SIZE}
        sub esp, 0x80
        mov eax, esp
        push 0
        push dword ptr [esi + edx + {RECORDS + 16}]
        push eax
        call 0x147440
        add esp, 12
        mov eax, esp
        push eax
        push 201
        call 0x284270
        add esp, 0x88
        push 1
    update_enabled:
        push 201
        call 0x284820
        add esp, 8
        pop eax
        jmp done
    apply_original:
        call {APPLY_UNDO:#x}
    """)

    # Only the two undo object-count reads use this wrapper. Zero keeps the
    # user's explicit undo-disable setting, and the native byte budget remains.
    read_limit = emit(f"""
        push ebp
        mov ebp, esp
        push dword ptr [ebp + 20]
        push dword ptr [ebp + 16]
        push dword ptr [ebp + 12]
        push dword ptr [ebp + 8]
        call {READ_PREFERENCE:#x}
        add esp, 16
        mov edx, dword ptr [ebp + 8]
        cmp word ptr [edx], 0
        je unchanged
        cmp word ptr [edx], {UNDO_OBJECT_LIMIT}
        jae unchanged
        mov word ptr [edx], {UNDO_OBJECT_LIMIT}
    unchanged:
        pop ebp
    """, frame=False)

    return bytes(code), (
        CallHook(0x1458BE, FREE_LIST, capture),
        CallHook(0x145E4E, FREE_LIST, cleanup),
        CallHook(0x1473EA, FREE_LIST, cleanup),
        CallHook(0x1458CB, REGISTER_UNDO, register),
        CallHook(0x145925, REGISTER_UNDO, register),
        CallHook(0x34EC4B, APPLY_UNDO, apply),
        CallHook(0x3B0E79, APPLY_UNDO, apply),
        CallHook(0x91FC2, PREPARE_UNDO, prepare),
        CallHook(0x1449B5, READ_PREFERENCE, read_limit),
        CallHook(0x145984, READ_PREFERENCE, read_limit),
    )
