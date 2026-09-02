package protocol

import "fmt"

const (
	BET     = 0
	DONE    = 1
	WINNERS = 2
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