package protocol

import (
	"fmt"
	"io"
	"strconv"
	"strings"

	"github.com/7574-sistemas-distribuidos/tp-nivelador/src/safe_socket"
)

const (
	BATCH   = 0
	DONE    = 1
	WINNERS = 2
	ACK     = 3
)

const HEADER_SIZE = 3

type Bet struct {
	AgencyId  int
	FirstName string
	LastName  string
	Document  int
	Birthdate string
	Number    int
}

// EncodeBet encodes a Bet struct into a byte slice for transmission over a network.
func EncodeBet(bet Bet) []byte {
	result := fmt.Sprintf("%d,%s,%s,%d,%s,%d", bet.AgencyId, bet.FirstName, bet.LastName, bet.Document, bet.Birthdate, bet.Number)
	return []byte(result)
}

// DecodeBet decodes a byte slice into a Bet struct.
func DecodeBet(payload []byte) (Bet, error) {
	payloadStr := string(payload)
	parts := strings.Split(payloadStr, ",")

	agencyId, err := strconv.Atoi(parts[0])
	if err != nil {
		return Bet{}, err
	}

	document, err := strconv.Atoi(parts[3])
	if err != nil {
		return Bet{}, err
	}

	number, err := strconv.Atoi(parts[5])
	if err != nil {
		return Bet{}, err
	}

	return Bet{
		AgencyId:  agencyId,
		FirstName: parts[1],
		LastName:  parts[2],
		Document:  document,
		Birthdate: parts[4],
		Number:    number,
	}, nil
}

// EncodeHeader encodes the message type and length into a byte slice for transmission over a network.
func EncodeHeader(msgType int, length uint16) []byte {
	header := make([]byte, HEADER_SIZE)
	header[0] = byte(msgType)
	header[1] = byte(length >> 8)
	header[2] = byte(length)

	return header
}

// DecodeHeader decodes a byte slice into the message type and length.
func DecodeHeader(header []byte) (int, uint16) {
	firstPart := header[1]
	secondPart := header[2]

	msgType := int(header[0])
	length := uint16(firstPart)<<8 | uint16(secondPart)

	return msgType, length
}

// EncodeWinners encodes a list of winning document numbers into a byte slice.
func EncodeWinners(winners []int) []byte {
	docString := []string{}
	for _, winner := range winners {
		docString = append(docString, strconv.Itoa(winner))
	}
	result := strings.Join(docString, ",")
	return []byte(result)
}

// DecodeWinners decodes bytes into a list of raw CSV rows (one per winner).
func DecodeWinners(payload []byte) ([]string, error) {
	payloadStr := string(payload)
	if payloadStr == "" {
		return []string{}, nil
	}
	return strings.Split(payloadStr, "\n"), nil
}

// SendMessage sends a message with the specified type and payload over the given connection.
func SendMessage(conn io.Writer, msgType int, payload []byte) error {
	header := EncodeHeader(msgType, uint16(len(payload)))
	message := append(header, payload...)
	return safe_socket.SendAll(conn, message)
}

// RecvMessage receives a message from the given connection, returning the message type and payload.
func RecvMessage(conn io.Reader) (int, []byte, error) {
	header, err := safe_socket.RecvAll(conn, HEADER_SIZE)
	if err != nil {
		return 0, nil, err
	}
	msgType, length := DecodeHeader(header)
	if length > 0 {
		payload, err := safe_socket.RecvAll(conn, int(length))
		if err != nil {
			return 0, nil, err
		}
		return msgType, payload, nil
	}
	if length == 0 {
		return msgType, []byte{}, nil
	}
	return 0, nil, fmt.Errorf("invalid message length: %d", length)
}

// EncodeBatch encodes a slice of Bet structs into a single byte slice for transmission over a network.
func EncodeBatch(bets []Bet) []byte {
	betStrings := []string{}
	for _, bet := range bets {
		betStrings = append(betStrings, string(EncodeBet(bet)))
	}
	result := strings.Join(betStrings, "\n")
	return []byte(result)
}

// DecodeBatch decodes a byte slice into a slice of Bet structs.
func DecodeBatch(payload []byte) ([]Bet, error) {
	payloadStr := string(payload)
	betStrings := strings.Split(payloadStr, "\n")

	bets := []Bet{}  

	for _, betStr := range betStrings {
		bet, err := DecodeBet([]byte(betStr))
		if err != nil {
			return nil, err
		}
		bets = append(bets, bet)
	}

	return bets, nil
}